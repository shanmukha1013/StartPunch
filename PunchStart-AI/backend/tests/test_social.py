def test_profile_update_and_view(make_client):
    a, ua = make_client("Ada", "ada@example.com")
    b, ub = make_client("Ben", "ben@example.com")
    r = a.patch("/api/me/profile", json={"headline": "Building fintech tools", "skills": ["Python", "ML"],
                                         "interests": ["fintech", "ai"], "looking_for": ["designer"],
                                         "links": {"website": "https://ada.example"}})
    assert r.status_code == 200 and r.json()["user"]["skills"] == ["Python", "ML"]
    assert a.patch("/api/me/profile", json={"links": {"website": "javascript:alert(1)"}}).status_code == 422
    profile = b.get(f"/api/users/{ua['handle']}").json()
    assert profile["headline"] == "Building fintech tools"
    assert "email" not in profile  # private field never exposed to others
    assert profile["relationship"]["following"] is False


def test_follow_counts_and_notification(make_client):
    a, ua = make_client("Ada", "ada@example.com")
    b, ub = make_client("Ben", "ben@example.com")
    assert b.post(f"/api/users/{ua['handle']}/follow").json() == {"following": True}
    b.post(f"/api/users/{ua['handle']}/follow")  # idempotent
    assert a.get(f"/api/users/{ua['handle']}").json()["follower_count"] == 1
    notes = a.get("/api/notifications").json()["notifications"]
    assert notes[0]["type"] == "follow"
    assert a.get("/api/notifications/unread-count").json()["notifications"] == 1
    a.post("/api/notifications/read", json={})
    assert a.get("/api/notifications/unread-count").json()["notifications"] == 0
    b.delete(f"/api/users/{ua['handle']}/follow")
    assert a.get(f"/api/users/{ua['handle']}").json()["follower_count"] == 0


def test_posts_likes_comments_reposts_bookmarks(make_client):
    a, ua = make_client("Ada", "ada@example.com")
    b, ub = make_client("Ben", "ben@example.com")
    post = a.post("/api/posts", json={"kind": "idea", "title": "AI bookkeeping", "body": "Feedback? #fintech #ai"}).json()
    assert post["tags"] == ["fintech", "ai"]
    assert b.post(f"/api/posts/{post['id']}/like").json()["liked"]
    b.post(f"/api/posts/{post['id']}/like")
    c1 = b.post(f"/api/posts/{post['id']}/comments", json={"body": "Love it"}).json()
    a.post(f"/api/posts/{post['id']}/comments", json={"body": "Thanks!", "parent_id": c1["id"]})
    b.post(f"/api/posts/{post['id']}/bookmark")
    repost = b.post(f"/api/posts/{post['id']}/repost", json={"comment": "Worth a look"}).json()
    assert repost["repost_of"]["id"] == post["id"]
    detail = a.get(f"/api/posts/{post['id']}").json()
    assert detail["counts"] == {"likes": 1, "comments": 2, "reposts": 1}
    comments = a.get(f"/api/posts/{post['id']}/comments").json()["comments"]
    assert comments[1]["parent_id"] == c1["id"]
    assert len(b.get("/api/bookmarks").json()["posts"]) == 1
    types = {n["type"] for n in a.get("/api/notifications").json()["notifications"]}
    assert {"like", "comment", "repost"} <= types
    assert b.patch(f"/api/posts/{post['id']}", json={"body": "hacked"}).status_code == 404  # not the author
    assert a.delete(f"/api/posts/{post['id']}").status_code == 200
    assert b.get(f"/api/posts/{post['id']}").status_code == 404


def test_followers_only_visibility_and_feeds(make_client):
    a, ua = make_client("Ada", "ada@example.com")
    b, ub = make_client("Ben", "ben@example.com")
    private = a.post("/api/posts", json={"body": "followers only update", "visibility": "followers"}).json()
    public = a.post("/api/posts", json={"body": "public update"}).json()
    assert b.get(f"/api/posts/{private['id']}").status_code == 404
    latest = [p["id"] for p in b.get("/api/feed?tab=latest").json()["posts"]]
    assert public["id"] in latest and private["id"] not in latest
    b.post(f"/api/users/{ua['handle']}/follow")
    following = [p["id"] for p in b.get("/api/feed?tab=following").json()["posts"]]
    assert {public["id"], private["id"]} <= set(following)
    for_you = b.get("/api/feed?tab=for_you").json()
    assert public["id"] in [p["id"] for p in for_you["posts"]]


def test_block_hides_content_and_prevents_contact(make_client):
    a, ua = make_client("Ada", "ada@example.com")
    b, ub = make_client("Ben", "ben@example.com")
    post = a.post("/api/posts", json={"body": "hello"}).json()
    b.post(f"/api/users/{ua['handle']}/follow")
    a.post(f"/api/users/{ub['handle']}/block")
    assert a.get(f"/api/users/{ua['handle']}").json()["follower_count"] == 0  # follow removed
    assert b.get(f"/api/posts/{post['id']}").status_code == 404
    assert b.get(f"/api/users/{ua['handle']}").status_code == 404
    assert b.post(f"/api/users/{ua['handle']}/follow").status_code == 403
    assert b.post("/api/conversations", json={"handle": ua["handle"]}).status_code == 422


def test_communities(make_client):
    a, ua = make_client("Ada", "ada@example.com")
    communities = a.get("/api/communities").json()["communities"]
    assert len(communities) == 12 and all(c["member_count"] == 0 for c in communities)
    assert a.post("/api/posts", json={"body": "hi", "community": "fintech"}).status_code == 403
    a.post("/api/communities/fintech/join")
    a.post("/api/posts", json={"body": "First fintech post", "community": "fintech"})
    detail = a.get("/api/communities/fintech").json()
    assert detail["community"]["joined"] and detail["community"]["member_count"] == 1
    assert detail["posts"][0]["community"]["slug"] == "fintech"
    a.delete("/api/communities/fintech/join")
    assert a.get("/api/communities/fintech").json()["community"]["member_count"] == 0


def test_startups_privacy_collaboration_and_messaging(make_client):
    a, ua = make_client("Ada", "ada@example.com")
    b, ub = make_client("Ben", "ben@example.com")
    private_id = a.post("/api/startups", json={"name": "Stealth", "tagline": "secret"}).json()["id"]
    assert b.get(f"/api/startups/{private_id}").status_code == 404
    public_id = a.post("/api/startups", json={"name": "OpenCo", "tagline": "AI bookkeeping for freelancers",
                                              "visibility": "public", "looking_for": ["designer"]}).json()["id"]
    assert [s["id"] for s in b.get("/api/startups").json()["startups"]] == [public_id]
    b.post(f"/api/startups/{public_id}/follow")
    assert b.post(f"/api/startups/{public_id}/collaborate", json={"role": "Designer", "message": "Keen to help"}).status_code == 201
    assert b.post(f"/api/startups/{public_id}/collaborate", json={"role": "Designer"}).status_code == 409
    # Ada only accepts messages from connections by default
    assert b.post("/api/conversations", json={"handle": ua["handle"]}).status_code == 403
    requests = a.get(f"/api/startups/{public_id}/collab-requests").json()["requests"]
    a.post(f"/api/collab-requests/{requests[0]['id']}/respond", json={"accept": True})
    conv = b.post("/api/conversations", json={"handle": ua["handle"]}).json()  # accepted collaboration allows messaging
    b.post(f"/api/conversations/{conv['id']}/messages", json={"body": "Hi Ada!"})
    inbox = a.get("/api/conversations").json()["conversations"]
    assert inbox[0]["unread"] == 1
    thread = a.get(f"/api/conversations/{conv['id']}/messages").json()
    assert thread["messages"][0]["body"] == "Hi Ada!"
    assert a.get("/api/conversations").json()["conversations"][0]["unread"] == 0
    assert b.post(f"/api/startups/{public_id}/analyze").status_code == 403  # founder did not allow AI analysis


def test_connections_flow(make_client):
    a, ua = make_client("Ada", "ada@example.com")
    b, ub = make_client("Ben", "ben@example.com")
    req = b.post("/api/connections", json={"handle": ua["handle"], "message": "Let's connect"}).json()
    assert req["status"] == "pending"
    incoming = a.get("/api/connections").json()["incoming"]
    assert incoming[0]["user"]["handle"] == ub["handle"]
    a.post(f"/api/connections/{incoming[0]['id']}/respond", json={"accept": True})
    assert len(b.get("/api/connections").json()["connections"]) == 1
    assert b.post("/api/conversations", json={"handle": ua["handle"]}).status_code == 200


def test_connections_only_profile(make_client):
    a, ua = make_client("Ada", "ada@example.com")
    b, ub = make_client("Ben", "ben@example.com")
    a.patch("/api/me/profile", json={"bio": "secret bio", "profile_visibility": "connections"})
    a.post("/api/posts", json={"body": "hello"})
    profile = b.get(f"/api/users/{ua['handle']}").json()
    assert profile.get("restricted") and "bio" not in profile
    assert b.get(f"/api/users/{ua['handle']}/posts").json()["restricted"]


def test_moderation(make_client):
    admin, _ = make_client("Admin", "admin@example.com")
    a, ua = make_client("Ada", "ada@example.com")
    b, ub = make_client("Ben", "ben@example.com")
    post = a.post("/api/posts", json={"body": "spammy spam"}).json()
    assert b.post("/api/moderation/reports", json={"entity_type": "post", "entity_id": post["id"], "reason": "spam"}).status_code == 201
    assert b.get("/api/moderation/reports").status_code == 403
    queue = admin.get("/api/moderation/reports").json()["reports"]
    assert queue[0]["preview"].startswith("spammy")
    admin.post(f"/api/moderation/reports/{queue[0]['id']}/resolve", json={"action": "hide"})
    assert b.get(f"/api/posts/{post['id']}").status_code == 404
    assert a.get(f"/api/posts/{post['id']}").json()["hidden"] is True  # author still sees it, marked hidden


def test_recommendations_explain_reasons(make_client):
    a, ua = make_client("Ada", "ada@example.com")
    b, ub = make_client("Ben", "ben@example.com")
    c, uc = make_client("Cy", "cy@example.com")
    a.patch("/api/me/profile", json={"interests": ["fintech", "ai"], "looking_for": ["designer"], "skills": ["python"]})
    b.patch("/api/me/profile", json={"interests": ["fintech"], "skills": ["product designer", "figma"]})
    c.patch("/api/me/profile", json={"interests": ["gardening"]})
    recs = a.get("/api/people/suggestions").json()
    handles = [r["user"]["handle"] for r in recs["people"]]
    assert handles == [ub["handle"]]  # Cy shares nothing: not recommended
    assert any("Shared interests" in reason for reason in recs["people"][0]["reasons"])
    assert recs["communities"][0]["slug"] in {"fintech", "ai-ml"}


def test_search_and_trending(make_client):
    a, ua = make_client("Ada", "ada@example.com")
    b, ub = make_client("Ben", "ben@example.com")
    post = a.post("/api/posts", json={"title": "Invoice automation", "body": "Thoughts on #invoicing?"}).json()
    b.post(f"/api/posts/{post['id']}/like")
    results = b.get("/api/search?q=invoice").json()
    assert results["posts"][0]["id"] == post["id"]
    trending = b.get("/api/trending").json()
    assert trending["tags"][0] == {"tag": "invoicing", "posts": 1}
    assert trending["posts"][0]["id"] == post["id"]


def test_media_upload_validation(make_client):
    a, ua = make_client("Ada", "ada@example.com")
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    up = a.post("/api/media", content=png, headers={"Content-Type": "image/png"})
    assert up.status_code == 201
    assert a.get(up.json()["url"]).content == png
    assert a.post("/api/media", content=b"<svg onload=alert(1)>", headers={"Content-Type": "image/svg+xml"}).status_code == 415
    a.patch("/api/me/profile", json={"avatar_media_id": up.json()["id"]})
    b, _ = make_client("Ben", "ben@example.com")
    assert b.patch("/api/me/profile", json={"avatar_media_id": up.json()["id"]}).status_code == 422  # not owner
