// ========================================================
// MentorConnect - Client-Side Interactive JavaScript
// ========================================================

document.addEventListener("DOMContentLoaded", () => {
    console.log("MentorConnect frontend UI initialized.");

    // 1. Mobile Navigation Toggle
    const mobileMenuBtn = document.getElementById("mobileMenuBtn");
    const navMenu = document.getElementById("navMenu");

    if (mobileMenuBtn && navMenu) {
        mobileMenuBtn.addEventListener("click", () => {
            navMenu.classList.toggle("open");
        });

        // Close menu when clicking outside on mobile
        document.addEventListener("click", (e) => {
            if (!navMenu.contains(e.target) && !mobileMenuBtn.contains(e.target)) {
                navMenu.classList.remove("open");
            }
        });
    }

    // 2. Client-Side Live Search / Filter for Mentor Cards
    const searchInput = document.getElementById("mentorSearchInput");
    const mentorCards = document.querySelectorAll(".mentor-card");

    if (searchInput && mentorCards.length > 0) {
        searchInput.addEventListener("input", (e) => {
            const query = e.target.value.toLowerCase().trim();

            mentorCards.forEach((card) => {
                const skills = card.getAttribute("data-skills") || "";
                const cardText = card.innerText.toLowerCase();

                if (skills.toLowerCase().includes(query) || cardText.includes(query)) {
                    card.style.display = "flex";
                } else {
                    card.style.display = "none";
                }
            });
        });
    }

    // 3. Auth Preview Modal Handling
    const authModal = document.getElementById("authModal");
    const modalTitle = document.getElementById("modalTitle");
    const modalDesc = document.getElementById("modalDesc");
    const modalCloseBtn = document.getElementById("modalCloseBtn");
    const authButtons = document.querySelectorAll(".js-auth-btn");

    function openAuthModal(action) {
        if (!authModal) return;

        if (action === "login") {
            modalTitle.textContent = "Log In to MentorConnect";
            modalDesc.textContent = "Welcome back! Enter your credentials to access your dashboard.";
        } else if (action === "register" || action === "register-mentee") {
            modalTitle.textContent = "Create Mentee Account";
            modalDesc.textContent = "Join MentorConnect to find experienced guides and book 1-on-1 sessions.";
        } else if (action === "register-mentor") {
            modalTitle.textContent = "Apply as a Mentor";
            modalDesc.textContent = "Share your knowledge and guide future engineers in their tech careers.";
        } else if (action === "request-mentor") {
            modalTitle.textContent = "Connect with Mentor";
            modalDesc.textContent = "You will be able to send personalized mentorship requests once logged in.";
        }

        authModal.classList.add("active");
    }

    window.closeAuthModal = function() {
        if (authModal) {
            authModal.classList.remove("active");
        }
    };

    authButtons.forEach((btn) => {
        btn.addEventListener("click", (e) => {
            e.preventDefault();
            const action = btn.getAttribute("data-action") || "login";
            openAuthModal(action);
        });
    });

    if (modalCloseBtn) {
        modalCloseBtn.addEventListener("click", closeAuthModal);
    }

    // Close modal when clicking on backdrop
    if (authModal) {
        authModal.addEventListener("click", (e) => {
            if (e.target === authModal) {
                closeAuthModal();
            }
        });
    }

    // 4. Auto-dismiss Flash Alerts
    const alerts = document.querySelectorAll(".alert");
    alerts.forEach((alert) => {
        setTimeout(() => {
            alert.style.transition = "opacity 0.5s ease";
            alert.style.opacity = "0";
            setTimeout(() => alert.remove(), 500);
        }, 4000);
    });
});
