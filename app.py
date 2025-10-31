from flask import Flask, flash, render_template, request, jsonify, session, redirect
from flask_mysqldb import MySQL
import MySQLdb.cursors
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_mysqldb import MySQL
from datetime import datetime
from uuid import uuid4
import requests, hashlib, base64, json, time
from phonepe.sdk.pg.payments.v2.standard_checkout_client import StandardCheckoutClient
from phonepe.sdk.pg.payments.v2.models.request.standard_checkout_pay_request import StandardCheckoutPayRequest
from phonepe.sdk.pg.common.models.request.meta_info import MetaInfo
from phonepe.sdk.pg.env import Env
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO
from flask import send_file


app = Flask(__name__)
app.secret_key = 'your_secret_key'

import os
from werkzeug.utils import secure_filename

# --- Upload Config ---
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create folder if not exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'medicine_store'

mysql = MySQL(app)

def generate_order_code():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT COUNT(*) AS count FROM orders")
    count = cursor.fetchone()['count'] + 1

    today = datetime.now().strftime("%Y%m%d")
    return f"ORD{today}{count:03d}"


# -------------------------------
# PHONEPE STANDARD CHECKOUT CONFIG
# -------------------------------
CLIENT_ID = "TEST-M2207DB8HUKKR_25101"        # your PhonePe client/merchant ID
CLIENT_SECRET = "ZDBkYTcyYmItYTliMS00NGJhLWE2ZWYtNzFjNWZjY2YwNjVj"  # your secret key
CLIENT_VERSION = 2                 # current SDK version
ENVIRONMENT = Env.SANDBOX          # change to Env.PRODUCTION when live
SHOULD_PUBLISH_EVENTS = False

client = StandardCheckoutClient.get_instance(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    client_version=CLIENT_VERSION,
    env=ENVIRONMENT,
    should_publish_events=SHOULD_PUBLISH_EVENTS
)


# ---------------------------
# HOME PAGE
# ---------------------------
@app.route('/')
def home():
    return render_template('login.html')


# ---------------------------
# LOGIN PAGE (GET)
# ---------------------------
@app.route('/login', methods=['GET'])
def login_page():
    return render_template('login.html')


# ---------------------------
# LOGIN ACTION (POST)
# ---------------------------
@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM users WHERE email=%s AND password=%s', (email, password))
    user = cursor.fetchone()

    if user:
        session['userid'] = user['id']
        session['user_name'] = user['first_name']
        session['user_email'] = user['email']
        return redirect('/products')
    else:
        return 'Invalid credentials! <a href="/login">Try again</a>'




# ---------------------------
# SIGNUP / REGISTRATION ROUTE
# ---------------------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        mobile = request.form['mobile']
        password = request.form['password']

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        account = cursor.fetchone()

        if account:
            return 'Account already exists! <a href="login">Login here</a>'
        else:
            cursor.execute(
                'INSERT INTO users (first_name, last_name, email, mobile, password) VALUES (%s, %s, %s, %s, %s)',
                (first_name, last_name, email, mobile, password)
            )
            mysql.connection.commit()
            return 'Registration successful! <a href="/login">Login now</a>'
    return render_template('signup.html')


# ---------------------------
# DASHBOARD 
# ---------------------------
@app.route('/dashboard')
def dashboard():
    if 'userid' not in session:
        return redirect('/login')

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Fetch user info
    cursor.execute("SELECT * FROM users WHERE id = %s", (session['userid'],))
    user = cursor.fetchone()

    # Fetch all user orders
    cursor.execute("SELECT * FROM orders WHERE userid = %s ORDER BY id DESC", (session['userid'],))
    orders = cursor.fetchall()

    # Fetch items for each order
    order_details = {}
    for order in orders:
        cursor.execute("SELECT * FROM order_items WHERE order_code = %s", (order['order_code'],))
        order_details[order['order_code']] = cursor.fetchall()

    return render_template('dashboard.html', user=user, orders=orders, order_details=order_details)

# ---------------------------
# LOGOUT
# ---------------------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ---------------------------
# profile UPDATE
# ---------------------------

@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'userid' not in session:
        return redirect('/login')

    first_name = request.form['first_name']
    last_name = request.form['last_name']
    email = request.form['email']
    mobile = request.form['mobile']
    address1 = request.form['address1']
    address2 = request.form['address2']
    city = request.form['city']
    state = request.form['state']
    pin_code = request.form['pin_code']

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("""
        UPDATE users 
        SET first_name=%s, last_name=%s, email=%s, mobile=%s, 
            address1=%s, address2=%s, city=%s, state=%s, pin_code=%s
        WHERE id=%s
    """, (first_name, last_name, email, mobile, address1, address2, city, state, pin_code, session['userid']))
    mysql.connection.commit()

    return redirect('/dashboard')

# ---------------------------
# Product
# ---------------------------

@app.route('/products')
def products():
    if 'userid' not in session:
        return redirect('/login')

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM products ORDER BY id DESC')
    products = cursor.fetchall()

    return render_template('products.html', products=products)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    if 'userid' not in session:
        return redirect('/login')

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Fetch selected product
    cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product = cursor.fetchone()

    if not product:
        return "Product not found", 404

    # Fetch similar products by brand (or category if available)
    cursor.execute("""
        SELECT * FROM products 
        WHERE brand = %s AND id != %s 
        ORDER BY RAND() LIMIT 4
    """, (product['brand'], product_id))
    similar_products = cursor.fetchall()

    return render_template('product_detail.html', product=product, similar_products=similar_products)


# ---------------------------
# ADD TO CART
# ---------------------------
@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    if 'userid' not in session:
        return jsonify({"status": "error", "message": "Login required"}), 401

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM products WHERE id = %s', (product_id,))
    product = cursor.fetchone()

    if not product:
        return jsonify({"status": "error", "message": "Product not found"}), 404

    cart = session.get('cart', [])

    existing_item = next((item for item in cart if item['id'] == product['id']), None)
    if existing_item:
        existing_item['quantity'] += 1
    else:
        cart.append({
            'id': product['id'],
            'name': product['name'],
            'price': float(product['price']),
            'discount': product['discount'],
            'image': product['image'],
            'quantity': 1
        })

    session['cart'] = cart

    return jsonify({
        "status": "success",
        "message": f"{product['name']} added to cart",
        "cart_count": len(cart)
    })
# ---------------------------
# VIEW CART
# ---------------------------
@app.route('/cart')
def view_cart():
    if 'userid' not in session:
        return redirect('/login')

    cart = session.get('cart', [])
    total = 0
    for item in cart:
        discounted = item['price'] - (item['price'] * item['discount'] / 100)
        total += discounted * item['quantity']

    # When AJAX calls for updated data
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            "cart": cart,
            "total": round(total, 2)
        })

    return render_template('cart.html', cart=cart, total=round(total, 2))


@app.route('/cart/update', methods=['POST'])
def update_cart_quantity():
    data = request.get_json()
    product_id = int(data['product_id'])
    action = data['action']

    cart = session.get('cart', [])
    for item in cart:
        if item['id'] == product_id:
            if action == 'increase':
                item['quantity'] += 1
            elif action == 'decrease':
                item['quantity'] -= 1
                if item['quantity'] <= 0:
                    cart = [i for i in cart if i['id'] != product_id]
            break

    session['cart'] = cart

    # Recalculate total
    total = 0
    for item in cart:
        discounted = item['price'] - (item['price'] * item['discount'] / 100)
        total += discounted * item['quantity']

    return jsonify({
        "cart": cart,
        "total": round(total, 2)
    })

# ---------------------------
# REMOVE ITEM FROM CART
# ---------------------------
@app.route('/remove_from_cart/<int:product_id>', methods=['GET', 'POST'])
def remove_from_cart(product_id):
    cart = session.get('cart', [])
    removed_item = None

    new_cart = []
    for item in cart:
        if item['id'] == product_id:
            removed_item = item
        else:
            new_cart.append(item)

    session['cart'] = new_cart

    # ✅ Always return JSON for AJAX requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if removed_item:
            return jsonify({
                "status": "success",
                "message": f"{removed_item['name']} removed from cart",
                "cart_count": len(new_cart),
                "total": sum(
                    (p['price'] - (p['price'] * p['discount'] / 100)) * p['quantity']
                    for p in new_cart
                )
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Item not found in cart",
                "cart_count": len(new_cart)
            }), 404

    # fallback for non-AJAX link clicks
    return redirect('/cart')




@app.route('/buy_now/<int:product_id>')
def buy_now(product_id):
    if 'userid' not in session:
        return redirect('/login')

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM products WHERE id = %s', (product_id,))
    product = cursor.fetchone()

    if not product:
        return "Product not found", 404

    # Store buy-now item in session
    session['buy_now_item'] = {
        'id': product['id'],
        'name': product['name'],
        'price': float(product['price']),
        'discount': product['discount'],
        'image': product['image'],
        'quantity': 1
    }

    # Redirect to same checkout route
    return redirect(url_for('checkout'))


@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'userid' not in session:
        return redirect('/login')

    buy_now_item = session.get('buy_now_item')
    cart = session.get('cart', [])

    if buy_now_item:
        items = [buy_now_item]
    elif cart and len(cart) > 0:
        items = cart
    else:
        flash("Your cart is empty. Please add products before checkout.", "warning")
        return redirect('/cart')
    
    total = sum((item['price'] - (item['price'] * item['discount'] / 100)) * item['quantity'] for item in items)

    if request.method == 'POST':
        address1 = request.form['address1']
        address2 = request.form['address2']
        city = request.form['city']
        state = request.form['state']
        pincode = request.form['pincode']
        payment_mode = request.form['payment_mode']

        order_code = generate_order_code()
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

        try:
            # Insert main order once
            cursor.execute("""
                INSERT INTO orders (order_code, userid, total, payment_mode, order_status)
                VALUES (%s, %s, %s, %s, %s)
            """, (order_code, session['userid'], total, payment_mode, 'Pending'))

            # Insert all order items
            for item in items:
                discounted_price = item['price'] - (item['price'] * item['discount'] / 100)
                item_total = discounted_price * item['quantity']

                cursor.execute("""
                    INSERT INTO order_items (order_code, product_id, product_name, quantity, price, discount, total)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    order_code,
                    item['id'],
                    item['name'],
                    item['quantity'],
                    item['price'],
                    item['discount'],
                    item_total
                ))

            mysql.connection.commit()

            session['order_code'] = order_code
            session['order_total'] = total

            # ✅ Fix: use `order_code` instead of `code`
            if payment_mode == 'PhonePe':
                return redirect('/phonepe_pay')
            else:
                session.pop('buy_now_item', None)
                session.pop('cart', None)
                return redirect(url_for('order_success', order_code=order_code))

        except Exception as e:
            mysql.connection.rollback()
            print("❌ Error inserting order:", str(e))
            return f"Database Error: {e}"
        finally:
            cursor.close()

    return render_template('checkout.html', cart=items, total=round(total, 2))


@app.route('/order_success')
def order_success():
    order_code = request.args.get('order_code')
    if not order_code:
        return redirect('/products')

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM orders WHERE order_code = %s", (order_code,))
    order = cursor.fetchone()

    if not order:
        cursor.close()
        return "Order not found!", 404

    cursor.execute("SELECT * FROM order_items WHERE order_code = %s", (order_code,))
    items = cursor.fetchall()
    cursor.close()

    return render_template('order_success.html', order=order, items=items)


@app.route('/phonepe_pay', methods=['GET'])
def phonepe_pay():
    if 'userid' not in session:
        return redirect('/login')

    # Retrieve the current order details
    order_code = session.get('order_code')
    total = session.get('order_total')

    if not order_code or not total:
        return "Order session missing. Please checkout again."

    try:
        # Convert amount to paisa
        amount_paise = int(float(total) * 100)
        merchant_order_id = order_code  # Use your own order_code instead of random uuid
        redirect_url = request.host_url + "phonepe_callback"

        # Prepare metadata
        meta_info = MetaInfo(
            udf1=str(session['userid']),
            udf2="MedicineStore",
            udf3="StandardCheckout"
        )

        # Build the PhonePe payment request
        pay_request = StandardCheckoutPayRequest.build_request(
            merchant_order_id=merchant_order_id,
            amount=amount_paise,
            redirect_url=redirect_url,
            meta_info=meta_info
        )

        # Create payment session
        pay_response = client.pay(pay_request)
        print("📦 Payment initialized for Order:", merchant_order_id)

        # Redirect user to PhonePe checkout page
        return redirect(pay_response.redirect_url)

    except Exception as e:
        print("❌ Error initiating PhonePe payment:", str(e))
        return f"Payment initialization failed: {e}"

@app.route('/phonepe_callback', methods=['GET', 'POST'])
def phonepe_callback():
    order_code = session.get('order_code')
    if not order_code:
        return "Invalid or expired transaction."

    cursor = None
    try:
        print(f"🔍 Checking PhonePe status for Order: {order_code}")

        # ✅ Get order status from PhonePe API
        response = client.get_order_status(order_code, details=True)
        print("📦 PhonePe Order Status Response:", response)

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

        # ✅ Safe extraction of transaction ID
        transaction_id = None
        if hasattr(response, 'transactionId') and response.transactionId:
            transaction_id = response.transactionId
        elif hasattr(response, 'data') and isinstance(response.data, dict):
            transaction_id = response.data.get('transactionId') or response.data.get('merchantTransactionId')
        elif hasattr(response, 'body') and isinstance(response.body, dict):
            transaction_id = response.body.get('transactionId')
        else:
            print("⚠️ No transaction ID found in response; using fallback order_code.")
            transaction_id = order_code  # fallback

        payment_state = getattr(response, "state", None) or getattr(response, "status", None)

        if not payment_state:
            return "Unable to determine payment status.", 400

        # ✅ Update order status
        if payment_state == "COMPLETED":
            cursor.execute("""
                UPDATE orders 
                SET order_status = 'Paid', 
                    payment_mode = 'PhonePe', 
                    transaction_id = %s
                WHERE order_code = %s
            """, (transaction_id, order_code))
            mysql.connection.commit()
            print(f"✅ Order {order_code} marked as Paid (Txn ID: {transaction_id})")
            
            send_invoice_email(order_code)


            # Fetch details for success page
            cursor.execute("SELECT * FROM orders WHERE order_code = %s", (order_code,))
            order = cursor.fetchone()
            cursor.execute("SELECT * FROM order_items WHERE order_code = %s", (order_code,))
            items = cursor.fetchall()

            # Cleanup session
            session.pop('cart', None)
            session.pop('buy_now_item', None)

            return render_template('order_success.html', order=order, items=items)

        elif payment_state == "FAILED":
            cursor.execute("""
                UPDATE orders 
                SET order_status = 'Failed', 
                    payment_mode = 'PhonePe', 
                    transaction_id = %s
                WHERE order_code = %s
            """, (transaction_id, order_code))
            mysql.connection.commit()
            print(f"❌ Order {order_code} marked as Failed.")
            return render_template('payment_failed.html', reason="Payment Failed")

        elif payment_state == "PENDING":
            cursor.execute("""
                UPDATE orders 
                SET order_status = 'Pending', 
                    payment_mode = 'PhonePe', 
                    transaction_id = %s
                WHERE order_code = %s
            """, (transaction_id, order_code))
            mysql.connection.commit()
            print(f"🕒 Order {order_code} still pending.")
            return "Payment is still pending. Please wait or check your order later."

        else:
            print(f"⚠️ Unknown payment state: {payment_state}")
            return f"Unknown payment status: {payment_state}"

    except Exception as e:
        print("❌ Error verifying payment:", str(e))
        return f"Error verifying payment: {e}"

    finally:
        if cursor:
            cursor.close()





from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from datetime import datetime
from io import BytesIO
from flask import send_file

@app.route('/download_invoice/<order_code>')
def download_invoice(order_code):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Fetch main order
    cursor.execute("SELECT * FROM orders WHERE order_code = %s", (order_code,))
    order = cursor.fetchone()
    if not order:
        cursor.close()
        return "Order not found!", 404

    # Fetch user details
    cursor.execute("SELECT first_name, last_name, email, mobile, address1, address2, city, state, pin_code FROM users WHERE id = %s", (order['userid'],))
    user = cursor.fetchone()

    # Fetch ordered items
    cursor.execute("SELECT * FROM order_items WHERE order_code = %s", (order_code,))
    items = cursor.fetchall()
    cursor.close()

    # Create PDF in memory
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 50

    # 🏪 Store Branding
    pdf.setFillColor(colors.HexColor("#007bff"))
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(50, y, "MEDICINE STORE")
    pdf.setFont("Helvetica", 10)
    pdf.setFillColor(colors.black)
    pdf.drawString(50, y - 15, "Your Trusted Healthcare Partner")
    pdf.drawString(50, y - 30, "Website: www.medicinestore.com | support@medicinestore.com")
    pdf.drawString(50, y - 45, f"Date: {datetime.now().strftime('%d-%m-%Y %I:%M %p')}")
    y -= 70

    # 🧾 Invoice Header
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(240, y, "INVOICE")
    y -= 25
    pdf.setFont("Helvetica", 11)
    pdf.drawString(50, y, f"Order Code: {order['order_code']}")
    pdf.drawString(300, y, f"Payment Mode: {order['payment_mode']}")
    y -= 15
    pdf.drawString(50, y, f"Order Status: {order['order_status']}")
    pdf.drawString(300, y, f"Total: ₹{order['total']}")
    y -= 30

    # 🧍 Customer Info
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Customer Information:")
    pdf.setFont("Helvetica", 10)
    y -= 15
    if user:
        full_name = f"{user['first_name']} {user['last_name']}"
        pdf.drawString(50, y, f"Name: {full_name}")
        y -= 15
        pdf.drawString(50, y, f"Email: {user['email']}")
        y -= 15
        pdf.drawString(50, y, f"Mobile: {user['mobile']}")
        y -= 15
        pdf.drawString(50, y, f"Address: {user['address1']}, {user['address2']}, {user['city']}, {user['state']} - {user['pin_code']}")
    else:
        pdf.drawString(50, y, "User details not found.")
    y -= 30

    # 🛍 Order Items
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Product")
    pdf.drawString(250, y, "Qty")
    pdf.drawString(300, y, "Price")
    pdf.drawString(370, y, "Discount")
    pdf.drawString(450, y, "Total")
    y -= 15
    pdf.line(50, y, 550, y)
    y -= 20

    pdf.setFont("Helvetica", 10)
    for item in items:
        if y < 100:  # New page if needed
            pdf.showPage()
            y = height - 50
            pdf.setFont("Helvetica", 10)

        pdf.drawString(50, y, item['product_name'])
        pdf.drawString(250, y, str(item['quantity']))
        pdf.drawString(300, y, f"₹{item['price']}")
        pdf.drawString(370, y, f"{item['discount']}%")
        pdf.drawString(450, y, f"₹{item['total']}")
        y -= 20

    pdf.line(50, y - 5, 550, y - 5)
    y -= 30

    # 💰 Grand Total
    pdf.setFont("Helvetica-Bold", 12)
    pdf.setFillColor(colors.HexColor("#28a745"))
    pdf.drawString(50, y, f"Grand Total: ₹{order['total']}")
    pdf.setFillColor(colors.black)
    y -= 40

    # 🖋️ Footer Notes
    pdf.setFont("Helvetica-Oblique", 9)
    pdf.setFillColor(colors.gray)
    pdf.drawString(50, y, "Thank you for shopping with Medicine Store!")
    y -= 12
    pdf.drawString(50, y, "For any issues, contact our support team at support@medicinestore.com")
    pdf.setFillColor(colors.black)

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Invoice_{order_code}.pdf",
        mimetype="application/pdf"
    )





# ---------------- ADMIN LOGIN ----------------
# ---------------------------
# ADMIN AUTHENTICATION
# ---------------------------

from functools import wraps
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect('/admin/login')
        return f(*args, **kwargs)
    return decorated


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT * FROM admin_users WHERE username=%s AND password=%s", (username, password))
        admin = cursor.fetchone()

        if admin:
            session['admin_logged_in'] = True
            session['admin_username'] = admin['username']
            return redirect('/admin/dashboard')
        else:
            return render_template('admin/login.html', error="Invalid username or password")

    return render_template('admin/login.html')


@app.route('/admin/logout')
@admin_required
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    return redirect('/admin/login')


@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Total Revenue
    cursor.execute("SELECT SUM(total) AS revenue FROM orders WHERE order_status = 'Paid'")
    total_revenue = cursor.fetchone()['revenue'] or 0

    # Total Orders
    cursor.execute("SELECT COUNT(*) AS total_orders FROM orders")
    total_orders = cursor.fetchone()['total_orders']

    # Paid, Pending, Failed orders
    cursor.execute("""
        SELECT 
            SUM(order_status = 'Paid') AS paid,
            SUM(order_status = 'Pending') AS pending,
            SUM(order_status = 'Failed') AS failed
        FROM orders
    """)
    status_data = cursor.fetchone()

    # Monthly Revenue trend (for chart)
    cursor.execute("""
        SELECT DATE_FORMAT(order_date, '%b') AS month, SUM(total) AS monthly_total
        FROM orders 
        WHERE order_status = 'Paid'
        GROUP BY MONTH(order_date)
        ORDER BY MONTH(order_date)
    """)
    monthly_data = cursor.fetchall()

    months = [row['month'] for row in monthly_data]
    revenue_values = [float(row['monthly_total']) for row in monthly_data]

    # Top Selling Products
    cursor.execute("""
        SELECT product_name, SUM(quantity) AS total_sold 
        FROM order_items 
        GROUP BY product_name 
        ORDER BY total_sold DESC 
        LIMIT 5
    """)
    top_products = cursor.fetchall()

    cursor.close()

    return render_template('admin/dashboard.html',
                           total_revenue=round(total_revenue, 2),
                           total_orders=total_orders,
                           paid=status_data['paid'],
                           pending=status_data['pending'],
                           failed=status_data['failed'],
                           months=months,
                           revenue_values=revenue_values,
                           top_products=top_products)
# ---------------------------
# ADMIN PRODUCT MANAGEMENT
# ---------------------------

@app.route('/admin/products')
@admin_required
def admin_products():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM products ORDER BY id DESC")
    products = cursor.fetchall()
    cursor.close()
    return render_template('admin/products.html', products=products)


# ---------------------------
# ADD PRODUCT (With File Upload)
# ---------------------------
@app.route('/admin/add_product', methods=['GET', 'POST'])
@admin_required
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        brand = request.form['brand']
        price = request.form['price']
        discount = request.form['discount']
        stock = request.form['stock']
        description = request.form['description']

        image_file = request.files.get('image')
        image_filename = None

        if image_file and allowed_file(image_file.filename):
            filename = secure_filename(image_file.filename)
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image_file.save(image_path)
            image_filename = f"uploads/{filename}"  # relative path for static folder

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("""
            INSERT INTO products (name, brand, price, discount, stock, description, image)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (name, brand, price, discount, stock, description, image_filename))
        mysql.connection.commit()
        cursor.close()

        flash("✅ Product added successfully!", "success")
        return redirect('/admin/products')

    return render_template('admin/add_product.html')


# ---------------------------
# EDIT PRODUCT (With File Upload)
# ---------------------------
@app.route('/admin/edit_product/<int:product_id>', methods=['GET', 'POST'])
@admin_required
def edit_product(product_id):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    if request.method == 'POST':
        name = request.form['name']
        brand = request.form['brand']
        price = request.form['price']
        discount = request.form['discount']
        stock = request.form['stock']
        description = request.form['description']

        image_file = request.files.get('image')
        image_filename = None

        if image_file and allowed_file(image_file.filename):
            filename = secure_filename(image_file.filename)
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image_file.save(image_path)
            image_filename = f"uploads/{filename}"

        # ✅ If no new image uploaded, keep old one
        if not image_filename:
            cursor.execute("SELECT image FROM products WHERE id=%s", (product_id,))
            old_image = cursor.fetchone()
            image_filename = old_image['image'] if old_image else None

        cursor.execute("""
            UPDATE products SET name=%s, brand=%s, price=%s, discount=%s, stock=%s, description=%s, image=%s
            WHERE id=%s
        """, (name, brand, price, discount, stock, description, image_filename, product_id))
        mysql.connection.commit()
        cursor.close()

        flash("✅ Product updated successfully!", "success")
        return redirect('/admin/products')

    cursor.execute("SELECT * FROM products WHERE id=%s", (product_id,))
    product = cursor.fetchone()
    cursor.close()
    return render_template('admin/edit_product.html', product=product)



@app.route('/admin/delete_product/<int:product_id>')
@admin_required
def delete_product(product_id):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("DELETE FROM products WHERE id=%s", (product_id,))
    mysql.connection.commit()
    cursor.close()
    flash("❌ Product deleted successfully!", "danger")
    return redirect('/admin/products')


# ---------------------------
# ADMIN: ORDERS MANAGEMENT
# ---------------------------
@app.route('/admin/orders', methods=['GET'])
@admin_required
def admin_orders():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)


    cursor.execute("SELECT COUNT(*) AS total_orders FROM orders")
    total_orders = cursor.fetchone()['total_orders']

    cursor.execute("SELECT COUNT(*) AS pending_orders FROM orders WHERE order_status='Pending'")
    pending_orders = cursor.fetchone()['pending_orders']

    cursor.execute("SELECT COUNT(*) AS completed_orders FROM orders WHERE order_status='Paid'")
    completed_orders = cursor.fetchone()['completed_orders']

    

    # Base query
    query = "SELECT o.*, u.first_name, u.last_name, u.email FROM orders o LEFT JOIN users u ON o.userid = u.id WHERE 1=1"
    filters = []

    # Filter parameters
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '').strip()
    payment_mode = request.args.get('payment_mode', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    page = int(request.args.get('page', 1))
    per_page = 10  # show 10 orders per page

    # Apply search filters
    if search:
        query += " AND (o.order_code LIKE %s OR u.first_name LIKE %s OR u.last_name LIKE %s OR u.email LIKE %s)"
        filters.extend([f"%{search}%"] * 4)

    if status:
        query += " AND o.order_status = %s"
        filters.append(status)

    if payment_mode:
        query += " AND o.payment_mode = %s"
        filters.append(payment_mode)

    if start_date and end_date:
        query += " AND DATE(o.order_date) BETWEEN %s AND %s"
        filters.extend([start_date, end_date])
    elif start_date:
        query += " AND DATE(o.order_date) >= %s"
        filters.append(start_date)
    elif end_date:
        query += " AND DATE(o.order_date) <= %s"
        filters.append(end_date)

    # Count total orders (for pagination)
    count_query = "SELECT COUNT(*) AS total FROM (" + query + ") AS total_orders"
    cursor.execute(count_query, tuple(filters))
    total_orders = cursor.fetchone()['total']

    total_pages = (total_orders + per_page - 1) // per_page
    offset = (page - 1) * per_page

    # Add limit for pagination
    query += " ORDER BY o.id DESC LIMIT %s OFFSET %s"
    filters.extend([per_page, offset])

    cursor.execute(query, tuple(filters))
    orders = cursor.fetchall()
    cursor.close()

    return render_template(
        'admin/orders.html',
        orders=orders,
        search=search,
        status=status,
        payment_mode=payment_mode,
        start_date=start_date,
        end_date=end_date,
        page=page,
        total_pages=total_pages,
        total_orders=total_orders,
        pending_orders=pending_orders,
        completed_orders=completed_orders,

    )


@app.route('/admin/order/<order_code>')
@admin_required
def admin_order_detail(order_code):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM orders WHERE order_code = %s", (order_code,))
    order = cursor.fetchone()
    cursor.execute("SELECT * FROM order_items WHERE order_code = %s", (order_code,))
    items = cursor.fetchall()
    cursor.close()
    return render_template('admin/order_detail.html', order=order, items=items)


@app.route('/admin/order/update_status/<order_code>', methods=['POST'])
@admin_required
def update_order_status(order_code):
    new_status = request.form['order_status']
    comment = request.form.get('admin_comment')

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("""
        UPDATE orders 
        SET order_status=%s, admin_comment=%s 
        WHERE order_code=%s
    """, (new_status, comment, order_code))
    mysql.connection.commit()
    cursor.close()
    flash("✅ Order status updated successfully!", "success")
    return redirect(f'/admin/order/{order_code}')


from phonepe.sdk.pg.common.models.request.refund_request import RefundRequest
from uuid import uuid4

@app.route('/admin/refund/<order_code>', methods=['POST'])
@admin_required
def process_refund(order_code):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM orders WHERE order_code = %s", (order_code,))
    order = cursor.fetchone()

    if not order:
        cursor.close()
        flash("❌ Order not found!", "danger")
        return redirect('/admin/orders')

    if order['order_status'] != 'Paid':
        cursor.close()
        flash("⚠️ Refund not allowed. Order is not marked as 'Paid'.", "warning")
        return redirect(f'/admin/order/{order_code}')

    try:
        refund_id = str(uuid4())  # Unique refund reference ID
        refund_amount_paise = int(float(order['total']) * 100)

        # ✅ Build the refund request
        refund_request = RefundRequest.build_refund_request(
            merchant_refund_id=refund_id,
            original_merchant_order_id=order_code,
            amount=refund_amount_paise
        )

        # ✅ Send refund request to PhonePe
        refund_response = client.refund(refund_request=refund_request)
        refund_state = getattr(refund_response, "state", "UNKNOWN")

        # ✅ Log response
        print(f"💸 Refund initiated for {order_code} | State: {refund_state}")

        # ✅ Update in database
        cursor.execute("""
            UPDATE orders 
            SET refund_id=%s, refund_state=%s, order_status='Refunded'
            WHERE order_code=%s
        """, (refund_id, refund_state, order_code))
        mysql.connection.commit()

        flash(f"✅ Refund {refund_state} for Order {order_code}", "success")

    except Exception as e:
        print("❌ Refund Error:", str(e))
        mysql.connection.rollback()
        flash(f"Error initiating refund: {e}", "danger")

    finally:
        cursor.close()

    return redirect(f'/admin/order/{order_code}')
@app.route('/admin/refund_status/<refund_id>')
@admin_required
def refund_status(refund_id):
    try:
        refund_response = client.get_refund_status(merchant_refund_id=refund_id)
        refund_state = getattr(refund_response, "state", "UNKNOWN")
        print(f"📦 Refund Status: {refund_state}")

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("""
            UPDATE orders 
            SET refund_state=%s
            WHERE refund_id=%s
        """, (refund_state, refund_id))
        mysql.connection.commit()
        cursor.close()

        flash(f"Refund Status Updated: {refund_state}", "info")
        return redirect('/admin/orders')

    except Exception as e:
        print("❌ Error checking refund:", str(e))
        return f"Error checking refund: {e}"


@app.route('/admin/complaints', methods=['GET', 'POST'])
@admin_required
def manage_complaints():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    if request.method == 'POST':
        order_code = request.form['order_code']
        complaint_text = request.form['complaint']

        cursor.execute("""
            UPDATE orders 
            SET complaint=%s
            WHERE order_code=%s
        """, (complaint_text, order_code))
        mysql.connection.commit()
        flash("🗣 Complaint added successfully!", "success")

    cursor.execute("SELECT order_code, userid, complaint, order_status FROM orders WHERE complaint IS NOT NULL ORDER BY id DESC")
    complaints = cursor.fetchall()
    cursor.close()

    return render_template('admin/complaints.html', complaints=complaints)

from flask_mail import Mail, Message

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'itsmdshabaz@gmail.com'   # your sender email
app.config['MAIL_PASSWORD'] = 'bjva ymts meoo ngcy'      # App password (not your login password)

mail = Mail(app)


@app.route('/admin/email_invoice/<order_code>', methods=['POST'])
def email_invoice(order_code):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Fetch order details
    cursor.execute("SELECT * FROM orders WHERE order_code = %s", (order_code,))
    order = cursor.fetchone()
    if not order:
        cursor.close()
        flash("Order not found!", "danger")
        return redirect('/admin/orders')

    # Fetch user info
    cursor.execute("SELECT first_name, last_name, email FROM users WHERE id = %s", (order['userid'],))
    user = cursor.fetchone()
    cursor.close()

    if not user or not user['email']:
        flash("Customer email not found!", "warning")
        return redirect('/admin/orders')

    # ✅ Generate PDF invoice in memory (reuse your existing PDF code)
    from io import BytesIO
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.drawString(100, 800, f"Invoice for Order: {order_code}")
    pdf.drawString(100, 780, f"Customer: {user['first_name']} {user['last_name']}")
    pdf.drawString(100, 760, f"Total Amount: ₹{order['total']}")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    # ✅ Prepare email
    msg = Message(
        subject=f"Your Invoice - Order {order_code}",
        sender=app.config['MAIL_USERNAME'],
        recipients=[user['email']],
        body=f"Hello {user['first_name']},\n\nThank you for your purchase!\nYour invoice for Order {order_code} is attached.\n\nRegards,\nMedicine Store"
    )

    # Attach PDF
    msg.attach(f"Invoice_{order_code}.pdf", "application/pdf", buffer.read())

    try:
        mail.send(msg)
        flash(f"Invoice emailed successfully to {user['email']}", "success")
    except Exception as e:
        print("❌ Email sending error:", str(e))
        flash("Failed to send invoice email. Please check email configuration.", "danger")

    return redirect('/admin/orders')


def send_invoice_email(order_code):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Fetch order and user details
    cursor.execute("SELECT * FROM orders WHERE order_code = %s", (order_code,))
    order = cursor.fetchone()
    cursor.execute("SELECT first_name, last_name, email FROM users WHERE id = %s", (order['userid'],))
    user = cursor.fetchone()
    cursor.close()

    if not user or not user['email']:
        print(f"⚠️ No email found for order {order_code}")
        return False

    # ✅ Generate PDF invoice in memory
    from io import BytesIO
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.drawString(100, 800, f"Invoice for Order: {order_code}")
    pdf.drawString(100, 780, f"Customer: {user['first_name']} {user['last_name']}")
    pdf.drawString(100, 760, f"Total Amount: ₹{order['total']}")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    # ✅ Prepare email
    msg = Message(
        subject=f"Your Invoice - Order {order_code}",
        sender=app.config['MAIL_USERNAME'],
        recipients=[user['email']],
        body=f"Hello {user['first_name']},\n\nThank you for your purchase!\nPlease find your invoice for Order {order_code} attached.\n\nRegards,\nMedicine Store"
    )
    msg.attach(f"Invoice_{order_code}.pdf", "application/pdf", buffer.read())

    try:
        mail.send(msg)
        print(f"✅ Invoice emailed to {user['email']} for order {order_code}")
        return True
    except Exception as e:
        print("❌ Error sending invoice:", e)
        return False


# --------------------------
# RUN APP
# --------------------------
if __name__ == "__main__":
    app.run(debug=True)
