import qrcode

def generate_qr(card_id):
    img = qrcode.make(card_id)
    img.save(f"qrs/{card_id}.png")
    print(f"QR code saved as: qrs/{card_id}.png")

# Example usage:
# generate_qr("123e4567-e89b-12d3-a456-426614174000")
