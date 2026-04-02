/* ============================================================
   main.js — Scroll animations, sticky nav, mobile menu
============================================================ */

(function () {
  "use strict";

  // ---- Sticky nav shadow on scroll ----
  const navbar = document.getElementById("navbar");
  window.addEventListener("scroll", function () {
    if (navbar) {
      if (window.scrollY > 20) {
        navbar.classList.add("scrolled");
      } else {
        navbar.classList.remove("scrolled");
      }
    }
  }, { passive: true });

  // Trigger once on load in case page is scrolled
  if (navbar && window.scrollY > 20) {
    navbar.classList.add("scrolled");
  }

  // ---- Mobile menu toggle ----
  const menuToggle = document.getElementById("menu-toggle");
  const mobileMenu = document.getElementById("mobile-menu");
  if (menuToggle && mobileMenu) {
    menuToggle.addEventListener("click", function () {
      const isOpen = !mobileMenu.classList.contains("hidden");
      if (isOpen) {
        mobileMenu.classList.add("hidden");
        menuToggle.classList.remove("open");
      } else {
        mobileMenu.classList.remove("hidden");
        menuToggle.classList.add("open");
      }
    });
  }

  // ---- Intersection Observer: scroll reveal ----
  const revealEls = document.querySelectorAll(".reveal");
  if (revealEls.length > 0) {
    const observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );
    revealEls.forEach(function (el) { observer.observe(el); });
  }
})();
