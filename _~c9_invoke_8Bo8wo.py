import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Personaly added in
from passlib.apps import custom_app_context as pwd_context

# Ensure environment variable is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Initialize the grand total starting with the user's current cash value
    cash = db.execute("SELECT cash FROM users WHERE id=:_id", _id=session["user_id"])
    grand_total = cash[0]["cash"]

    # List each stock symbol and its quantity of shares from portfolio table
    symbol_shares = db.execute("SELECT symbol, shares FROM portfolio WHERE id=:_id",
                               _id=session["user_id"])

    # Update stock price and add to grand total
    for row in symbol_shares:
        symbol = symbol_shares["symbol"]
        shares = symbol_shares["shares"]
        stock = lookup(symbol)
        total = stock["price"] * shares
        db.execute("UPDATE portfolio SET price=:price, total=:total WHERE symbol=:symbol",
                   price=usd(stock["price"]), symbol=symbol)
        # Add stock value to the grand total
        grand_total += total

    # Array of all portfolio data
    portfolio = db.execute("SELECT * FROM portfolio WHERE id=:_id", _id=session["user_id"])

    return render_template("index.html", portfolio=portfolio, cash=usd(cash[0]["cash"]),
                           grand_total=grand_total)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        # Retrieve stock symbol
        stock = lookup(request.form.get("symbol"))
        if not stock:
            return apology("stock symbol not found")

        # Retrieve number of shares
        shares = int(request.form.get("shares"))
        if shares < 0:
            return apology("must input positive value")

        # Grab user funds
        cash = db.execute("SELECT cash FROM users Where id = :_id", _id=session["user_id"])

        # Check if they're sufficient
        if stock["price"] * shares > float(cash[0]["cash"]):
            return apology("insufficient funds")

        # Store transaction in portfolio
        db.execute("INSERT INTO portfolio (symbol, shares, price, u_id) VALUES (:symbol, :shares, :price, :u_id)",
                   symbol=stock["symbol"], shares=shares, price=stock["price"], u_id=session["user_id"])

        # Update user's funds
        db.execute("UPDATE users SET cash = cash - :cost WHERE id=user_id",
                   cost=shares*stock["price"], user_id=session["user_id"])

        return redirect(url_for("index"))

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    return apology("TODO")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":

        # Recieve stock symbol from quote form
        quote = lookup(request.form.get("symbol"))
        if not quote:
            return apology("stock symbol not found")
        else:
            quote['price'] = usd(quote['price'])
            # http://flask.pocoo.org/docs/1.0/quickstart/
            # Render quoted stock
            return render_template("quote.html", quote=quote)
    else:
        # If quote!=quote, render form
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure password confirmation was submitted
        elif not request.form.get("password-confirm"):
            return apology("must confirm password")

        # Ensure passwords match
        elif not request.form.get("password") != request.form.get("confirm_password"):
            return apology("passwords must match", 403)

        # Insert username and hash into database, and provide that info in an array
        # https://www.sqlite.org/lang_expr.html
        # Hash password
        # https://passlib.readthedocs.io/en/1.6.5/new_app_quickstart.html
        # NOTE: db.execute returns a list of dictionaries. Contained as [{key,value},{key,value},...]
        result = db.execute("INSERT INTO users (username, hash) VALUES (:username, :_hash)",
                            username=request.form.get("username"),
                            _hash=pwd_context.hash(request.form.get("password")))
        if not result:
            return apology("username taken, choose another", 403)

        # Keep user logged in during session
        # https://pythonhosted.org/Flask-Session/
        user_id = db.execute("SELECT id FROM users WHERE username = :username",
                             username=request.form.get("username"))
        session["user_id"] = user_id[0]["id"]

        # Take user back to main page
        # http://flask.pocoo.org/docs/0.12/quickstart/#url-building
        # http://flask.pocoo.org/docs/0.12/api/
        return redirect(url_for("index"))
        # Alternative status code(the current from redirect being 302)
        # https://en.wikipedia.org/wiki/List_of_HTTP_status_codes
        # https://stackoverflow.com/questions/14343812/redirecting-to-url-in-flask
        # Partial explanation as to why one would use redirect vs. render_template
        # https://stackoverflow.com/questions/21668481/difference-between-render-template-and-redirect

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    


def errorhandler(e):
    """Handle error"""
    return apology(e.name, e.code)


# listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
