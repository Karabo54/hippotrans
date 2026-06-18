from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
import os

def create_pdf(inv):
    file_path = f"data/invoices/INV_{inv['order_number']}.pdf"
    os.makedirs('data/invoices', exist_ok=True)
    c = canvas.Canvas(file_path, pagesize=A4)
    width, height = A4

    # --- Logo & Header ---
    logo_path = "data/logo.png"
    if os.path.exists(logo_path):
        c.drawImage(logo_path, 50, height - 80, width=60, height=60, preserveAspectRatio=True)
    
    c.setFont("Helvetica-Bold", 16)
    c.drawString(120, height - 50, "YOUR COMPANY NAME")
    c.setFont("Helvetica", 9)
    c.drawString(120, height - 65, "123 Logistics Way, Ficksburg | VAT: 4123456789")

    # --- Invoice Info ---
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(width - 50, height - 50, "TAX INVOICE")
    c.setFont("Helvetica", 10)
    c.drawRightString(width - 50, height - 65, f"INV #: {inv['inv_no']}")
    c.drawRightString(width - 50, height - 78, f"Date: {inv['date']}")

    # --- Bill To ---
    c.line(50, height - 100, width - 50, height - 100)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, height - 120, "BILL TO:")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 135, f"{inv['customer']}")
    c.drawString(50, height - 148, f"{inv['address']}")
    c.drawString(50, height - 161, f"VAT: {inv['vat_no']}")

    # --- Table Header ---
    y = height - 220
    c.setFillColor(colors.lightgrey)
    c.rect(50, y, width - 100, 20, fill=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, y + 6, "DESCRIPTION")
    c.drawRightString(width - 60, y + 6, "TOTAL")

    # --- Calculation Logic ---
    y -= 30
    litres = float(inv.get('litres', 0))
    rate = float(inv.get('rate', 0))
    subtotal = litres * rate
    vat_rate = float(inv.get('vat', 15)) / 100
    vat_amount = subtotal * vat_rate
    grand_total = subtotal + vat_amount

    # --- Line Item ---
    c.setFont("Helvetica", 10)
    c.drawString(60, y, f"Transport: {inv['route']} ({litres:,.0f}L @ R {rate:,.2f})")
    c.drawRightString(width - 60, y, f"R {subtotal:,.2f}")

    # --- Totals Section ---
    y -= 40
    c.line(width - 200, y, width - 50, y)
    y -= 20
    c.drawString(width - 200, y, "SUBTOTAL")
    c.drawRightString(width - 60, y, f"R {subtotal:,.2f}")
    
    y -= 15
    c.drawString(width - 200, y, f"VAT ({inv['vat']}%)")
    c.drawRightString(width - 60, y, f"R {vat_amount:,.2f}")
    
    y -= 20
    c.setFont("Helvetica-Bold", 11)
    c.drawString(width - 200, y, "TOTAL DUE")
    c.drawRightString(width - 60, y, f"R {grand_total:,.2f}")

    # --- Banking (Bottom) ---
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, 100, "BANKING DETAILS:")
    c.setFont("Helvetica", 10)
    c.drawString(50, 85, "Bank: FNB | Acc: 62123456789 | Branch: 250655")
    c.drawString(50, 72, f"Reference: {inv['inv_no']}")

    c.showPage()
    c.save()
    return file_path