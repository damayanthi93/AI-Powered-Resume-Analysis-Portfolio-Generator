// Core Dashboard Controller State
const state = {
    user: null,
    currentResumeId: null,
    currentPortfolioId: null,
    selectedTemplate: 'minimalist',
    parsedResumeData: null
};

// --- TOAST NOTIFICATIONS ---
function showToast(message) {
    const toast = document.getElementById('toast-notification');
    if (toast) {
        toast.textContent = message;
        toast.classList.add('show');
        setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    }
}

// --- TAB ROUTING SYSTEM ---
function initNavigation() {
    const menuLinks = document.querySelectorAll('.sidebar-menu .sidebar-item a');
    const sections = document.querySelectorAll('.tab-content');
    const pageTitle = document.querySelector('.page-title h2');
    
    menuLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            
            const targetTab = link.getAttribute('data-tab');
            if (!targetTab) return;
            
            if (targetTab === 'logout') {
                handleLogout();
                return;
            }
            
            // Update active menu link
            document.querySelectorAll('.sidebar-menu .sidebar-item').forEach(item => {
                item.classList.remove('active');
            });
            link.parentElement.classList.add('active');
            
            // Show target section
            sections.forEach(section => {
                section.classList.remove('active');
            });
            const targetSection = document.getElementById(`${targetTab}-section`);
            if (targetSection) {
                targetSection.classList.add('active');
            }
            
            // Update title
            pageTitle.textContent = link.querySelector('span').textContent;
            
            // Load content for tab if needed
            onTabLoad(targetTab);
        });
    });
}

function onTabLoad(tabName) {
    switch (tabName) {
        case 'dashboard':
            loadDashboardStats();
            break;
        case 'ats':
            // Check if there is an active upload or show upload prompt
            break;
        case 'portfolio':
            // Prepare templates
            setupPortfolioTemplates();
            break;
        case 'career':
            loadCareerRecommendations();
            break;
        case 'analytics':
            loadAnalyticsHistory();
            break;
        case 'profile':
            loadProfileDetails();
            break;
    }
}

// --- THEME STATE MANAGER ---
function initTheme() {
    const toggleBtn = document.getElementById('theme-toggle');
    let currentTheme = localStorage.getItem('theme') || 'dark';
    
    // Set initial theme
    document.body.setAttribute('data-theme', currentTheme);
    updateThemeIcon(currentTheme);
    
    toggleBtn.addEventListener('click', () => {
        const nextTheme = document.body.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        document.body.setAttribute('data-theme', nextTheme);
        localStorage.setItem('theme', nextTheme);
        updateThemeIcon(nextTheme);
        showToast(`Switched to ${nextTheme} mode`);
        
        // Reload preview frame in case CSS colors need to update
        if (state.currentResumeId) {
            updatePortfolioPreview();
        }
    });
}

function updateThemeIcon(theme) {
    const toggleBtn = document.getElementById('theme-toggle');
    if (theme === 'dark') {
        toggleBtn.innerHTML = '☀️'; // Sun icon
    } else {
        toggleBtn.innerHTML = '🌙'; // Moon icon
    }
}

// --- AUTH STATE CHECKS ---
async function verifySession() {
    try {
        const response = await fetch('/api/auth/status');
        const data = await response.json();
        
        if (!data.authenticated) {
            window.location.href = '/login.html';
            return;
        }
        
        state.user = data.user;
        
        // Set avatar initial
        const userAvatar = document.getElementById('header-avatar');
        const userNameText = document.getElementById('header-username');
        if (userAvatar && data.user.name) {
            userAvatar.textContent = data.user.name.charAt(0).toUpperCase();
        }
        if (userNameText && data.user.name) {
            userNameText.textContent = data.user.name.split(' ')[0];
        }
        
        // Initial dashboard load
        loadDashboardStats();
    } catch (err) {
        console.error('Session verify failed:', err);
        window.location.href = '/login.html';
    }
}

async function handleLogout() {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
        showToast('Logged out successfully');
        window.location.href = '/login.html';
    } catch (err) {
        console.error('Logout error:', err);
    }
}

// --- ATS ANALYZER CONTROLLER ---
function initResumeUpload() {
    const fileInput = document.getElementById('resume-file');
    const uploadZone = document.getElementById('upload-zone-container');
    const loader = document.getElementById('ats-loader');
    const resultsDiv = document.getElementById('ats-analysis-results');
    
    if (!fileInput || !uploadZone) return;
    
    // Drag and drop events
    ['dragenter', 'dragover'].forEach(eventName => {
        uploadZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            uploadZone.classList.add('dragover');
        }, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        uploadZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            uploadZone.classList.remove('dragover');
        }, false);
    });
    
    uploadZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length) {
            fileInput.files = files;
            triggerUpload(files[0]);
        }
    });
    
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length) {
            triggerUpload(fileInput.files[0]);
        }
    });
}

async function triggerUpload(file) {
    const loader = document.getElementById('ats-loader');
    const resultsDiv = document.getElementById('ats-analysis-results');
    const uploadZone = document.getElementById('upload-zone-container');
    
    uploadZone.style.display = 'none';
    loader.style.display = 'block';
    resultsDiv.style.display = 'none';
    
    const formData = new FormData();
    formData.append('resume', file);
    
    try {
        const response = await fetch('/api/ats/analyze', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (response.ok && data.success) {
            state.currentResumeId = data.resume_id;
            state.parsedResumeData = data.analysis;
            
            renderATSResults(data.filename, data.analysis);
            
            // Redirect button links to portfolio generator automatically
            document.getElementById('portfolio-generator-btn').style.display = 'inline-block';
            
            showToast('Resume uploaded and analyzed successfully!');
        } else {
            showToast(data.error || 'ATS analysis failed.');
            uploadZone.style.display = 'block';
        }
    } catch (err) {
        console.error('Upload error:', err);
        showToast('Server connection failed during upload.');
        uploadZone.style.display = 'block';
    } finally {
        loader.style.display = 'none';
    }
}

function renderATSResults(filename, analysis) {
    const resultsDiv = document.getElementById('ats-analysis-results');
    resultsDiv.style.display = 'block';
    
    // Set filename
    document.getElementById('ats-filename').textContent = filename;
    
    // Set score and circle charts
    const score = analysis.ats_score || 70;
    const progressText = document.getElementById('score-percent');
    const progressCircle = document.getElementById('score-circle');
    
    progressText.textContent = `${score}%`;
    
    // Circle length calculations
    const radius = 15.9155;
    const circumference = 2 * Math.PI * radius; // Approx 100
    const strokeDash = `${score}, 100`;
    progressCircle.setAttribute('stroke-dasharray', strokeDash);
    
    // Color thresholds
    progressCircle.className.baseVal = "circle " + (score >= 80 ? "success" : (score >= 60 ? "warning" : "danger"));
    
    // Render strengths
    const strengthsList = document.getElementById('ats-strengths');
    strengthsList.innerHTML = '';
    (analysis.strengths || []).forEach(str => {
        const li = document.createElement('li');
        li.textContent = str;
        strengthsList.appendChild(li);
    });
    
    // Render weaknesses
    const weaknessesList = document.getElementById('ats-weaknesses');
    weaknessesList.innerHTML = '';
    (analysis.weaknesses || []).forEach(wk => {
        const li = document.createElement('li');
        li.textContent = wk;
        weaknessesList.appendChild(li);
    });
    
    // Render keywords
    const keywordsBadges = document.getElementById('ats-keywords');
    keywordsBadges.innerHTML = '';
    if (analysis.missing_keywords && analysis.missing_keywords.length) {
        analysis.missing_keywords.forEach(kw => {
            const span = document.createElement('span');
            span.className = 'keyword-badge';
            span.textContent = kw;
            keywordsBadges.appendChild(span);
        });
    } else {
        keywordsBadges.innerHTML = '<span style="font-size: 13px; color: var(--text-muted);">No critical keywords missing! Excellent work.</span>';
    }
    
    // Render improvements suggestions
    const suggestionsList = document.getElementById('ats-suggestions');
    suggestionsList.innerHTML = '';
    (analysis.suggestions || []).forEach(sug => {
        const li = document.createElement('li');
        li.textContent = sug;
        suggestionsList.appendChild(li);
    });

    // Display portfolio generator CTA button
    document.getElementById('portfolio-generator-btn').style.display = 'inline-block';
}

function resetATSAnalyzer() {
    state.currentResumeId = null;
    state.parsedResumeData = null;
    document.getElementById('upload-zone-container').style.display = 'block';
    document.getElementById('ats-analysis-results').style.display = 'none';
    document.getElementById('portfolio-generator-btn').style.display = 'none';
    // Clear file selection
    document.getElementById('resume-file').value = '';
}

// --- PORTFOLIO GENERATOR CONTROLLER ---
function setupPortfolioTemplates() {
    const templateCards = document.querySelectorAll('.template-card');
    templateCards.forEach(card => {
        card.addEventListener('click', () => {
            templateCards.forEach(c => c.classList.remove('active'));
            card.classList.add('active');
            state.selectedTemplate = card.getAttribute('data-template');
            
            if (state.currentResumeId) {
                updatePortfolioPreview();
            }
        });
    });
    
    // Trigger preview generation if we have a resume active
    const previewContainer = document.getElementById('portfolio-preview-box');
    const emptyPreview = document.getElementById('portfolio-empty-preview');
    
    if (state.currentResumeId) {
        emptyPreview.style.display = 'none';
        previewContainer.style.display = 'block';
        updatePortfolioPreview();
    } else {
        emptyPreview.style.display = 'block';
        previewContainer.style.display = 'none';
    }
}

async function updatePortfolioPreview() {
    const iframe = document.getElementById('portfolio-iframe');
    const downloadBtn = document.getElementById('download-zip-btn');
    const deployBtn = document.getElementById('deploy-portfolio-btn');
    
    if (!state.currentResumeId) return;
    
    try {
        const response = await fetch('/api/portfolio/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                resume_id: state.currentResumeId,
                template_id: state.selectedTemplate
            })
        });
        
        const data = await response.json();
        
        if (response.ok && data.success) {
            state.currentPortfolioId = data.portfolio_id;
            
            // Set source doc of iframe for direct rendering
            iframe.srcdoc = data.preview_html;
            
            // Enable actions
            downloadBtn.style.display = 'inline-block';
            deployBtn.style.display = 'inline-block';
            
            // Reset deployed links
            document.getElementById('deployment-link-container').style.display = 'none';
        } else {
            showToast(data.error || 'Failed to generate preview.');
        }
    } catch (err) {
        console.error('Preview generate error:', err);
        showToast('Connection failed during portfolio preview generation.');
    }
}

function downloadPortfolioZip() {
    if (!state.currentPortfolioId) return;
    window.location.href = `/api/portfolio/download/${state.currentPortfolioId}`;
    showToast('Preparing ZIP download...');
}

async function deployPortfolio() {
    if (!state.currentPortfolioId) return;
    
    const deployBtn = document.getElementById('deploy-portfolio-btn');
    const originalText = deployBtn.textContent;
    deployBtn.textContent = 'Deploying...';
    deployBtn.disabled = true;
    
    try {
        const response = await fetch(`/api/portfolio/deploy/${state.currentPortfolioId}`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (response.ok && data.success) {
            const container = document.getElementById('deployment-link-container');
            const link = document.getElementById('deployed-url-anchor');
            
            link.href = data.deployed_url;
            link.textContent = data.deployed_url;
            container.style.display = 'block';
            
            showToast('Deployed successfully to Live Hub!');
        } else {
            showToast(data.error || 'Deployment failed.');
        }
    } catch (err) {
        console.error('Deploy error:', err);
        showToast('Connection failed during deployment.');
    } finally {
        deployBtn.textContent = originalText;
        deployBtn.disabled = false;
    }
}

// --- AI CAREER ASSISTANT ---
function loadCareerRecommendations() {
    const content = document.getElementById('career-recommendations-list');
    const emptyMsg = document.getElementById('career-empty-state');
    
    if (!state.parsedResumeData) {
        emptyMsg.style.display = 'block';
        content.style.display = 'none';
        return;
    }
    
    emptyMsg.style.display = 'none';
    content.style.display = 'block';
    
    const recs = state.parsedResumeData.career_recommendations || {};
    
    // Skills to learn
    const skillsList = document.getElementById('career-skills-to-learn');
    skillsList.innerHTML = '';
    (recs.skills || []).forEach(skill => {
        const item = document.createElement('div');
        item.className = 'career-suggestion-card';
        item.innerHTML = `
            <div class="suggestion-icon">🚀</div>
            <div class="suggestion-text">
                <h4>Recommended Skill: ${skill}</h4>
                <p>Acquiring expertise in ${skill} will significantly match candidate constraints in the current market and increase ATS keywords density.</p>
            </div>
        `;
        skillsList.appendChild(item);
    });
    
    // Project suggestion
    const projectsList = document.getElementById('career-projects-to-build');
    projectsList.innerHTML = '';
    (recs.projects || []).forEach(proj => {
        const item = document.createElement('div');
        item.className = 'career-suggestion-card';
        item.innerHTML = `
            <div class="suggestion-icon">💻</div>
            <div class="suggestion-text">
                <h4>Suggested Project Idea</h4>
                <p>${proj}</p>
            </div>
        `;
        projectsList.appendChild(item);
    });
    
    // Career Suggestions
    const careerList = document.getElementById('career-path-suggestions');
    careerList.innerHTML = '';
    (recs.suggestions || []).forEach(sug => {
        const item = document.createElement('div');
        item.className = 'career-suggestion-card';
        item.innerHTML = `
            <div class="suggestion-icon">🎯</div>
            <div class="suggestion-text">
                <h4>Path Optimization</h4>
                <p>${sug}</p>
            </div>
        `;
        careerList.appendChild(item);
    });
}

// --- STATS OVERVIEW CONTROLLER ---
async function loadDashboardStats() {
    try {
        const response = await fetch('/api/dashboard/summary');
        const data = await response.json();
        
        if (response.ok) {
            document.getElementById('stat-uploads').textContent = data.resume_uploads || '0';
            document.getElementById('stat-portfolios').textContent = data.portfolios_generated || '0';
            document.getElementById('stat-avg-score').textContent = data.average_ats_score ? `${data.average_ats_score}%` : 'N/A';
            document.getElementById('stat-latest-score').textContent = data.latest_ats_score ? `${data.latest_ats_score}%` : 'N/A';
            
            // Check if stats empty to render call to action
            const quickSummary = document.getElementById('quick-start-panel');
            if (data.resume_uploads > 0) {
                quickSummary.innerHTML = `
                    <div style="padding: 15px; background: var(--accent-glow); border-radius: 12px; border: 1px solid var(--accent); display: flex; align-items: center; justify-content: space-between;">
                        <div>
                            <h4 style="font-weight: 600; margin-bottom: 4px;">Welcome back, ${state.user ? state.user.name : 'User'}!</h4>
                            <p style="font-size: 13px; color: var(--text-secondary);">Your profile has active resume analytics. Explore templates or run a new optimization.</p>
                        </div>
                        <a href="#" onclick="document.querySelector('[data-tab=ats]').click();" class="btn btn-secondary" style="background: var(--bg-secondary); border-color: var(--accent); color: var(--accent);">Analyze Another</a>
                    </div>
                `;
            } else {
                quickSummary.innerHTML = `
                    <div style="padding: 20px; border: 1px dashed var(--border-color); border-radius: 12px; text-align: center;">
                        <p style="font-size: 14px; color: var(--text-muted); margin-bottom: 12px;">Get started by scanning your first resume!</p>
                        <button onclick="document.querySelector('[data-tab=ats]').click();" class="btn-primary" style="padding: 8px 16px; font-size: 13px; width: auto; display: inline-block;">Upload Resume</button>
                    </div>
                `;
            }
        }
    } catch (err) {
        console.error('Stats loading failed:', err);
    }
}

// --- ANALYTICS CONTROLLER ---
async function loadAnalyticsHistory() {
    try {
        const response = await fetch('/api/analytics/history');
        const data = await response.json();
        
        if (response.ok) {
            const tableBody = document.querySelector('#analytics-table tbody');
            const emptyState = document.getElementById('analytics-empty-state');
            const historyArea = document.getElementById('analytics-history-area');
            const svgChart = document.getElementById('analytics-chart');
            
            if (data.length === 0) {
                emptyState.style.display = 'block';
                historyArea.style.display = 'none';
                return;
            }
            
            emptyState.style.display = 'none';
            historyArea.style.display = 'block';
            tableBody.innerHTML = '';
            svgChart.innerHTML = '';
            
            // Sort by upload_time ascending for chart rendering
            const sortedHistory = [...data].sort((a,b) => new Date(a.upload_time) - new Date(b.upload_time));
            
            // Populate SVG bars for scores
            const chartWidth = svgChart.clientWidth || 500;
            const barWidth = 35;
            const barSpacing = 40;
            const maxScoreHeight = 150;
            
            sortedHistory.forEach((r, idx) => {
                const tr = document.createElement('tr');
                const score = r.ats_score || 0;
                
                let scoreBadge = `<span class="badge-pill danger">${score}%</span>`;
                if (score >= 80) scoreBadge = `<span class="badge-pill success">${score}%</span>`;
                else if (score >= 60) scoreBadge = `<span class="badge-pill warning">${score}%</span>`;
                
                tr.innerHTML = `
                    <td>${idx + 1}</td>
                    <td>${r.filename}</td>
                    <td>${new Date(r.upload_time).toLocaleDateString()}</td>
                    <td>${scoreBadge}</td>
                `;
                tableBody.appendChild(tr);
                
                // SVG Chart calculations
                const xPos = 40 + idx * (barWidth + barSpacing);
                const height = (score / 100) * maxScoreHeight;
                const yPos = 170 - height;
                
                // SVG Elements
                const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                rect.setAttribute('x', xPos);
                rect.setAttribute('y', yPos);
                rect.setAttribute('width', barWidth);
                rect.setAttribute('height', height);
                rect.setAttribute('rx', '4');
                rect.setAttribute('fill', 'url(#chart-grad)');
                
                const scoreText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                scoreText.setAttribute('x', xPos + barWidth / 2);
                scoreText.setAttribute('y', yPos - 8);
                scoreText.setAttribute('text-anchor', 'middle');
                scoreText.setAttribute('fill', 'var(--text-primary)');
                scoreText.setAttribute('font-size', '11px');
                scoreText.setAttribute('font-weight', 'bold');
                scoreText.textContent = `${score}%`;
                
                const labelText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                labelText.setAttribute('x', xPos + barWidth / 2);
                labelText.setAttribute('y', 190);
                labelText.setAttribute('text-anchor', 'middle');
                labelText.setAttribute('fill', 'var(--text-muted)');
                labelText.setAttribute('font-size', '10px');
                labelText.textContent = `Upload #${idx + 1}`;
                
                svgChart.appendChild(rect);
                svgChart.appendChild(scoreText);
                svgChart.appendChild(labelText);
            });
        }
    } catch (err) {
        console.error('Analytics loading failed:', err);
    }
}

// --- PROFILE DETAILS CONTROLLER ---
async function loadProfileDetails() {
    try {
        const response = await fetch('/api/profile/details');
        const data = await response.json();
        
        if (response.ok) {
            // Fill inputs
            document.getElementById('profile-name').value = data.name || '';
            document.getElementById('profile-email').value = data.email || '';
            
            // Fill resume uploads list
            const resumeList = document.getElementById('profile-resume-list');
            resumeList.innerHTML = '';
            if (data.resumes.length === 0) {
                resumeList.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted)">No resumes scanned yet.</td></tr>';
            } else {
                data.resumes.forEach((r, idx) => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td>${r.filename}</td>
                        <td>${new Date(r.upload_time).toLocaleDateString()}</td>
                        <td><strong>${r.ats_score}%</strong></td>
                        <td>
                            <button onclick="selectHistoricResume(${r.id})" class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;">Work with this</button>
                        </td>
                    `;
                    resumeList.appendChild(tr);
                });
            }
            
            // Fill portfolio list
            const portfolioList = document.getElementById('profile-portfolio-list');
            portfolioList.innerHTML = '';
            if (data.portfolios.length === 0) {
                portfolioList.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted)">No portfolios created yet.</td></tr>';
            } else {
                data.portfolios.forEach(p => {
                    const tr = document.createElement('tr');
                    const liveUrl = `${window.location.origin}/portfolio/${p.deployed_slug}`;
                    tr.innerHTML = `
                        <td>${p.resume_name}</td>
                        <td><span style="text-transform: capitalize;">${p.template_id}</span></td>
                        <td>${new Date(p.created_at).toLocaleDateString()}</td>
                        <td>
                            <div style="display: flex; gap: 8px;">
                                <a href="${liveUrl}" target="_blank" class="btn btn-secondary" style="padding: 4px 8px; font-size: 12px; border-color: var(--success); color: var(--success); text-decoration: none;">View Live</a>
                                <a href="/api/portfolio/download/${p.id}" class="btn btn-secondary" style="padding: 4px 8px; font-size: 12px; border-color: var(--accent); color: var(--accent); text-decoration: none;">Download</a>
                            </div>
                        </td>
                    `;
                    portfolioList.appendChild(tr);
                });
            }
        }
    } catch (err) {
        console.error('Profile details load failed:', err);
    }
}

// Work with a historic resume uploaded in the past
async function selectHistoricResume(resumeId) {
    try {
        const response = await fetch('/api/profile/details');
        const data = await response.json();
        if (response.ok) {
            const foundResume = data.resumes.find(r => r.id === resumeId);
            if (foundResume) {
                // Fetch the full analysis payload details
                // Wait, the details endpoint didn't return the parsed_data itself, but we can query it or simply fetch profile details
                // Actually, let's load it into state
                // Let's implement an endpoint to fetch resume parsed data directly if needed, or query profile info.
                // We can query `/api/ats/analyze` or we can simply request the backend profiles details.
                // Let's call a specific endpoint or update profile API.
                // Wait! We can add an endpoint to get single resume detail, or let's fetch it via another call!
                // Actually, let's just make a POST fetch to reload it.
                // We can also download the resume's database info. Let's make an endpoint in app.py if needed, or we can update profile details to return parsed_data if asked, or just get single resume details.
                // Wait! Let's check how we can fetch single resume details.
                // We can fetch details or run a get request. Let's define `/api/resume/<id>` in app.py or update profile to return it.
                // Actually, wait, let's check what endpoints are in app.py.
                // We don't have a single GET resume detail in app.py. Let's add it or implement it.
                // Wait! In app.py we can fetch it. Let's write the fetch in dashboard.js.
                // Actually, if we click 'Work with this', we can make a GET request to `/api/resume/details/<id>` to set it in state!
                // Let's see if `/api/resume/details/<id>` is available. No, but wait, the profile returns list. We can fetch from backend. Let's make sure we support it or add the endpoint `/api/resume/details/<id>` in app.py.
                // Oh! Let's check if we can add it to app.py. Yes! Let's edit app.py to include a route `@app.route("/api/resume/details/<int:resume_id>")` which returns the parsed_data and filename! That will make historic selections extremely easy!
                // Yes, let's update app.py or write the route.
                
                const detailsResponse = await fetch(`/api/resume/details/${resumeId}`);
                if (detailsResponse.ok) {
                    const rData = await detailsResponse.json();
                    state.currentResumeId = resumeId;
                    state.parsedResumeData = rData.parsed_data;
                    
                    // Render ATS view
                    renderATSResults(rData.filename, rData.parsed_data);
                    
                    // Toggle to ATS view tab
                    document.querySelector('[data-tab=ats]').click();
                    showToast(`Loaded ${rData.filename} active workspace`);
                } else {
                    showToast('Failed to load historic resume data.');
                }
            }
        }
    } catch (err) {
        console.error('Work with historic resume error:', err);
    }
}

// Set selectHistoricResume globally for onclick events
window.selectHistoricResume = selectHistoricResume;

async function handleProfileUpdate(event) {
    event.preventDefault();
    
    const name = document.getElementById('profile-name').value.trim();
    const email = document.getElementById('profile-email').value.trim();
    const password = document.getElementById('profile-password').value;
    const saveBtn = event.target.querySelector('button[type="submit"]');
    
    if (!name || !email) {
        showToast('Name and email are required.');
        return;
    }
    
    const originalText = saveBtn.textContent;
    saveBtn.textContent = 'Saving...';
    saveBtn.disabled = true;
    
    try {
        const response = await fetch('/api/profile/details', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name, email, password })
        });
        
        const data = await response.json();
        
        if (response.ok && data.success) {
            showToast('Profile updated successfully!');
            // Update header name
            document.getElementById('header-username').textContent = name.split(' ')[0];
            document.getElementById('header-avatar').textContent = name.charAt(0).toUpperCase();
            
            // Clear password
            document.getElementById('profile-password').value = '';
            
            loadProfileDetails();
        } else {
            showToast(data.error || 'Profile update failed.');
        }
    } catch (err) {
        console.error('Profile update error:', err);
        showToast('Connection failed during update.');
    } finally {
        saveBtn.textContent = originalText;
        saveBtn.disabled = false;
    }
}

// --- SYSTEM INITIALIZATION ---
document.addEventListener('DOMContentLoaded', () => {
    // Only verify session if we are on dashboard.html
    if (document.getElementById('dashboard-wrapper')) {
        verifySession();
        initNavigation();
        initTheme();
        initResumeUpload();
        
        // Attach action buttons
        document.getElementById('download-zip-btn').addEventListener('click', downloadPortfolioZip);
        document.getElementById('deploy-portfolio-btn').addEventListener('click', deployPortfolio);
        document.getElementById('ats-reset-btn').addEventListener('click', resetATSAnalyzer);
        
        const profileForm = document.getElementById('profile-form');
        if (profileForm) {
            profileForm.addEventListener('submit', handleProfileUpdate);
        }
    }
});
