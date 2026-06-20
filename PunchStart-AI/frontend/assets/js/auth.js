document.addEventListener('DOMContentLoaded', () => {
    const formStep = document.getElementById('login-form-step');
    const welcomeStep = document.getElementById('welcome-step');
    const button = document.getElementById('create-session-btn');
    const error = document.getElementById('auth-error');

    if (localStorage.getItem('auth_token')) {
        window.location.href = 'dashboard.html';
        return;
    }

    button.addEventListener('click', () => {
        const name = document.getElementById('founder-name').value.trim();
        const email = document.getElementById('founder-email').value.trim();
        if (!name || !email || !email.includes('@')) {
            error.textContent = 'Enter a founder name and valid email to continue.';
            return;
        }

        localStorage.setItem('auth_token', `local-${Date.now()}`);
        localStorage.setItem('user', JSON.stringify({ firstName: name.split(' ')[0], name, email }));
        formStep.classList.add('hidden');
        welcomeStep.classList.remove('hidden');
        setTimeout(() => {
            window.location.href = 'dashboard.html';
        }, 700);
    });
});
