// Authentication Helper Functions

function showAuthAlert(message, type = 'danger') {
    const alertBox = document.getElementById('auth-alert');
    if (alertBox) {
        alertBox.textContent = message;
        alertBox.className = `alert alert-${type}`;
        alertBox.style.display = 'block';
    }
}

async function handleLogin(event) {
    event.preventDefault();
    
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;
    const submitBtn = event.target.querySelector('button[type="submit"]');
    
    if (!email || !password) {
        showAuthAlert('Please fill in all fields.');
        return;
    }
    
    // Disable button & show spinner
    const originalText = submitBtn.textContent;
    submitBtn.textContent = 'Logging in...';
    submitBtn.disabled = true;
    
    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ email, password })
        });
        
        const data = await response.json();
        
        if (response.ok && data.success) {
            window.location.href = '/dashboard.html';
        } else {
            showAuthAlert(data.error || 'Invalid credentials. Please try again.');
            submitBtn.textContent = originalText;
            submitBtn.disabled = false;
        }
    } catch (err) {
        console.error('Login error:', err);
        showAuthAlert('Failed to connect to backend server.');
        submitBtn.textContent = originalText;
        submitBtn.disabled = false;
    }
}

async function handleSignup(event) {
    event.preventDefault();
    
    const name = document.getElementById('name').value.trim();
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;
    const confirmPassword = document.getElementById('confirmPassword').value;
    const submitBtn = event.target.querySelector('button[type="submit"]');
    
    if (!name || !email || !password || !confirmPassword) {
        showAuthAlert('Please fill in all fields.');
        return;
    }
    
    if (password !== confirmPassword) {
        showAuthAlert('Passwords do not match.');
        return;
    }
    
    if (password.length < 6) {
        showAuthAlert('Password must be at least 6 characters.');
        return;
    }
    
    // Disable button & show loading state
    const originalText = submitBtn.textContent;
    submitBtn.textContent = 'Creating Account...';
    submitBtn.disabled = true;
    
    try {
        const response = await fetch('/api/auth/signup', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name, email, password })
        });
        
        const data = await response.json();
        
        if (response.ok && data.success) {
            window.location.href = '/dashboard.html';
        } else {
            showAuthAlert(data.error || 'Registration failed. Try again.');
            submitBtn.textContent = originalText;
            submitBtn.disabled = false;
        }
    } catch (err) {
        console.error('Signup error:', err);
        showAuthAlert('Failed to connect to backend server.');
        submitBtn.textContent = originalText;
        submitBtn.disabled = false;
    }
}

// Check auth status on page load (redirect if already logged in)
async function checkAuthOnAuthPages() {
    try {
        const response = await fetch('/api/auth/status');
        const data = await response.json();
        if (data.authenticated) {
            window.location.href = '/dashboard.html';
        }
    } catch (err) {
        console.warn('Unable to verify auth status.', err);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Check if we are on login or signup pages
    const loginForm = document.getElementById('login-form');
    const signupForm = document.getElementById('signup-form');
    
    if (loginForm || signupForm) {
        checkAuthOnAuthPages();
    }
    
    if (loginForm) {
        loginForm.addEventListener('submit', handleLogin);
    }
    
    if (signupForm) {
        signupForm.addEventListener('submit', handleSignup);
    }
});
