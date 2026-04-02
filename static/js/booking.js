/* ============================================================
   booking.js — Full booking + Razorpay flow
   Handles: validation, availability check, order creation,
            Razorpay modal, payment verification, WhatsApp redirect.
============================================================ */
(function () {
  "use strict";

  // ---- DOM References ----
  const form         = document.getElementById("booking-form");
  const payBtn       = document.getElementById("pay-btn");
  const payBtnText   = document.getElementById("pay-btn-text");
  const payBtnSpinner= document.getElementById("pay-btn-spinner");
  const availStatus  = document.getElementById("availability-status");
  const successPanel = document.getElementById("success-panel");
  const slotCards    = document.querySelectorAll(".slot-card");
  const dateInput    = document.getElementById("date");
  const slotInputs   = document.querySelectorAll('input[name="slot"]');

  // ---- Set minimum date to today ----
  const today = new Date().toISOString().split("T")[0];
  if (dateInput) dateInput.setAttribute("min", today);

  // ---- Highlight selected slot card ----
  slotCards.forEach(function (card) {
    const radio = card.querySelector('input[type="radio"]');
    if (radio && radio.checked) card.classList.add("selected");

    card.addEventListener("click", function () {
      slotCards.forEach(function (c) { c.classList.remove("selected"); });
      card.classList.add("selected");
      if (radio) radio.checked = true;
      triggerAvailabilityCheck();
    });
  });

  // ---- Availability check on date change ----
  if (dateInput) {
    dateInput.addEventListener("change", triggerAvailabilityCheck);
  }

  // ---- Availability check helper ----
  let availCheckTimeout = null;
  function triggerAvailabilityCheck() {
    clearTimeout(availCheckTimeout);
    availCheckTimeout = setTimeout(checkAvailability, 300);
  }

  function getSelectedSlot() {
    for (var i = 0; i < slotInputs.length; i++) {
      if (slotInputs[i].checked) return slotInputs[i].value;
    }
    return null;
  }

  async function checkAvailability() {
    const date = dateInput ? dateInput.value : null;
    const slot = getSelectedSlot();

    if (!date || !slot) return;

    showAvailabilityStatus("checking", "Checking availability...");
    clearSlotBadges();

    try {
      const res = await fetch("/check-availability", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date: date, slot: slot }),
      });
      const data = await res.json();

      if (!res.ok) {
        showAvailabilityStatus("unavailable", data.error || "Invalid request.");
        return;
      }

      if (data.available) {
        showAvailabilityStatus(
          "available",
          "This slot is available on " + formatDate(date) + "."
        );
        setSlotBadge(slot, true);
      } else {
        showAvailabilityStatus(
          "unavailable",
          data.message || "This slot is already booked."
        );
        setSlotBadge(slot, false);
      }
    } catch (err) {
      showAvailabilityStatus("unavailable", "Could not check availability. Please try again.");
    }
  }

  function showAvailabilityStatus(type, msg) {
    if (!availStatus) return;
    availStatus.className = "mb-6 p-4 rounded-xl text-sm font-medium " + type;
    availStatus.textContent = msg;
    availStatus.classList.remove("hidden");
  }

  function clearSlotBadges() {
    document.querySelectorAll(".slot-badge").forEach(function (b) {
      b.className = "slot-badge absolute top-2 right-2 text-xs px-2 py-0.5 rounded-full hidden";
      b.textContent = "";
    });
  }

  function setSlotBadge(slotVal, isAvailable) {
    var card = document.querySelector('.slot-card[data-slot="' + slotVal + '"]');
    if (!card) return;
    var badge = card.querySelector(".slot-badge");
    if (!badge) return;
    badge.classList.remove("hidden");
    if (isAvailable) {
      badge.className = "slot-badge available-badge absolute top-2 right-2 text-xs px-2 py-0.5 rounded-full";
      badge.textContent = "Free";
    } else {
      badge.className = "slot-badge unavailable-badge absolute top-2 right-2 text-xs px-2 py-0.5 rounded-full";
      badge.textContent = "Booked";
    }
  }

  function formatDate(dateStr) {
    var d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" });
  }

  // ---- Form Validation ----
  function showError(id, msg) {
    var el = document.getElementById(id + "-error");
    if (el) { el.textContent = msg; el.classList.remove("hidden"); }
  }
  function clearError(id) {
    var el = document.getElementById(id + "-error");
    if (el) { el.textContent = ""; el.classList.add("hidden"); }
  }
  function clearAllErrors() {
    ["name", "phone", "event_type", "date", "slot"].forEach(clearError);
  }

  function validateForm() {
    clearAllErrors();
    var valid = true;

    var name = document.getElementById("name").value.trim();
    var phone = document.getElementById("phone").value.trim();
    var eventType = document.getElementById("event_type").value.trim();
    var date = dateInput ? dateInput.value.trim() : "";
    var slot = getSelectedSlot();

    if (!name) { showError("name", "Please enter your full name."); valid = false; }
    if (!phone || phone.length !== 10 || !/^\d{10}$/.test(phone)) {
      showError("phone", "Please enter a valid 10-digit mobile number."); valid = false;
    }
    if (!eventType) { showError("event_type", "Please select your event type."); valid = false; }
    if (!date) { showError("date", "Please select an event date."); valid = false; }
    else if (date < today) { showError("date", "Please select a future date."); valid = false; }
    if (!slot) { showError("slot", "Please select a time slot."); valid = false; }

    return valid;
  }

  // ---- Set button loading state ----
  function setLoading(isLoading, msg) {
    payBtn.disabled = isLoading;
    payBtnText.textContent = msg || (isLoading ? "Processing..." : "Send Booking Request");
    if (payBtnSpinner) {
      if (isLoading) payBtnSpinner.classList.remove("hidden");
      else payBtnSpinner.classList.add("hidden");
    }
  }

  // ---- Form Submit → Request flow ----
  if (form) {
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      if (!validateForm()) return;

      setLoading(true, "Sending request...");

      var name      = document.getElementById("name").value.trim();
      var phone     = document.getElementById("phone").value.trim();
      var eventType = document.getElementById("event_type").value.trim();
      var date      = dateInput.value.trim();
      var slot      = getSelectedSlot();

      // 1. Create booking request
      var orderData;
      try {
        var orderRes = await fetch("/create-order", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: name,
            phone: phone,
            event_type: eventType,
            date: date,
            slot: slot,
          }),
        });
        orderData = await orderRes.json();
        if (!orderRes.ok) {
          showAvailabilityStatus("unavailable", orderData.error || "Failed to create request.");
          setLoading(false);
          return;
        }
      } catch (err) {
        showAvailabilityStatus("unavailable", "Network error. Please try again.");
        setLoading(false);
        return;
      }

      setLoading(false, "Send Booking Request");

      // 2. Show success & redirect to WhatsApp
      form.classList.add("hidden");
      successPanel.classList.remove("hidden");
      var pidEl = document.getElementById("success-payment-id");
      if (pidEl) pidEl.textContent = "Your request is under review.";

      setTimeout(function () {
        window.location.href = orderData.whatsapp_url;
      }, 2500);

    });
  }
})();
