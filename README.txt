FISH MARKETPLACE

1. Install Python 3.10 or newer.
2. Open this folder in VS Code.
3. Open Terminal and run:
   pip install -r requirements.txt
4. Start the website:
   python app.py
5. Open:
   http://127.0.0.1:5000

ADMIN LOGIN
Address: http://127.0.0.1:5000/admin/login
Username: admin
Password: ChangeMe123!

Change the default password before sharing or deploying the website.
For deployment, set these environment variables:
SECRET_KEY = a long random secret
ADMIN_USERNAME = your chosen admin username
ADMIN_PASSWORD = your strong admin password
WHATSAPP_NUMBER = your number in international digits only, e.g. 201001234567

CUSTOMER FEATURES
- Browse and search fish.
- View fish descriptions, recommended food, price, and stock.
- Submit an order through the website.
- Open WhatsApp to send the order details.

ADMIN FEATURES
- Secure admin login.
- Add, edit, and delete fish.
- Upload fish photos.
- Manage stock and prices.
- View orders and update their status.

IMPORTANT
This first version records orders but does not collect online card payments.
A payment provider can be integrated in a later step.
The included SQLite database and uploaded images are stored locally. Before deploying
to a public hosting service, configure persistent database and image storage so orders
and uploaded photos are not lost when the hosting service restarts or redeploys.
