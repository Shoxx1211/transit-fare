ton.addEventListener("click", function () {
    const cardId = cardSelect.value;

    if (!cardId) {
      messageDiv.innerHTML = "❌ Please select a card";
      return;
    }

    if (!navigator.geolocation) {
      messageDiv.innerHTML = "❌ Geolocation is not supported by your browser";
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const latitude = position.coords.latitude;
        const longitude = position.coords.longitude;

        fetch("/nfc_tap", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ card_id: cardId, latitude, longitude }),
        })
          .then((response) => response.json())
          .then((data) => {
            messageDiv.innerHTML = data.message;
          })
          .catch((error) => {
            console.error("Error:", error);
            messageDiv.innerHTML = "❌ An error occurred during NFC tap.";
          });
      },
