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


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # [1] Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # Ensure password confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("must confirm password")

        # Ensure passwords match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords must match")

        # [2][3] Insert username and hash into database, and place that info into an array
        result = db.execute("INSERT INTO users (username, hash) VALUES (:username, :_hash)",
                            username=request.form.get("username"),
                            _hash=generate_password_hash(request.form.get("password")))
        if not result:
            return apology("username taken, choose another")

        # [4] Keep user logged in during session
        _id = db.execute("SELECT id FROM users WHERE username = :username",
                         username=request.form.get("username"))
        session["user_id"] = _id[0]["id"]

        # [5][6][7] Take user back to main page
        return redirect("/")

    else:
        # [8] Render page so user can fill form
        return render_template("register.html")


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
        symbol = row["symbol"]
        shares = row["shares"]
        stock = lookup(symbol)
        total = stock["price"] * shares
        db.execute("UPDATE portfolio SET price=:price, total=:total WHERE symbol=:symbol",
                   price=usd(stock["price"]), total=usd(total), symbol=symbol)
        # Add stock value to the grand total
        grand_total += total

    # Array of all portfolio data
    portfolio = db.execute("SELECT * FROM portfolio WHERE id=:_id", _id=session["user_id"])

    # [9] helpers.py does not provide a dictionary with three keys as stated
    return render_template("index.html", portfolio=portfolio, cash=usd(cash[0]["cash"]),
                           grand_total=usd(grand_total))


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
            return render_template("quote.html", quote=quote)
    else:
        # If quote!=quote, render form
        return render_template("quote.html")


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":

        # Retrieve stock symbol
        stock = lookup(request.form.get("symbol"))
        if not request.form.get("symbol"):
            return apology("stock symbol not found")

        # [10] Retrieve number of shares
        try:
            shares = int(request.form.get("shares"))
            if shares < 0:
                return apology("must be a positive whole number")
        except:
            return apology("must be a positive whole number")

        # Grab user funds
        cash = db.execute("SELECT cash FROM users Where id=:_id", _id=session["user_id"])

        # Check if they're sufficient
        if stock["price"] * shares > float(cash[0]["cash"]):
            return apology("insufficient funds", 403)

        # [11] Check if stock exists within portfolio
        holdings = db.execute("SELECT shares FROM portfolio WHERE id=:_id AND symbol=:symbol",
                              _id=session["user_id"], symbol=stock["symbol"])
        # Update if stock exists
        if holdings:
            db.execute("UPDATE portfolio SET price= price+:price, shares= shares+:shares WHERE id=:_id AND symbol=:symbol",
                       price=stock["price"], shares=shares, _id=session["user_id"], symbol=stock["symbol"])
            db.execute("INSERT INTO history (symbol, shares, price, total, id) VALUES (:symbol, :shares, :price, :total, :_id)",
                       symbol=stock["symbol"], shares=shares, price=stock["price"], total=stock["price"]*shares, _id=session["user_id"])
        # Insert if it doesn't
        else:
            db.execute("INSERT INTO portfolio (symbol, shares, price, total, id) VALUES (:symbol, :shares, :price, :total, :_id)",
                       symbol=stock["symbol"], shares=shares, price=stock["price"], total=stock["price"]*shares, _id=session["user_id"])
            db.execute("INSERT INTO history (symbol, shares, price, total, id) VALUES (:symbol, :shares, :price, :total, :_id)",
                       symbol=stock["symbol"], shares=shares, price=stock["price"], total=stock["price"]*shares, _id=session["user_id"])

        # Update user's funds
        db.execute("UPDATE users SET cash= cash-:cost WHERE id=:_id", cost=stock["price"]*shares, _id=session["user_id"])

        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":

        # Retrieve stock symbol
        try:
            stock = lookup(request.form.get("symbol"))
        except:
            return apology("no stocks held")

        # Retrieve number of shares
        try:
            shares = int(request.form.get("shares"))
            if shares <= 0:
                return apology("must be a positive whole number")
        except:
            return apology("must be a positive whole number")

        # Check if there are shares in portfolio and if there are enough
        holdings = db.execute("SELECT shares FROM portfolio WHERE id=:_id AND symbol=:symbol",
                              _id=session["user_id"], symbol=stock["symbol"])
        if not holdings:
            return apology("stock is not in portfolio", 403)
        if shares > holdings[0]["shares"]:
            return apology("quantity of shares are insufficient")

        # Update portfolio
        db.execute("UPDATE portfolio SET shares= shares-:shares WHERE id=:_id AND symbol=:symbol",
                   shares=shares, _id=session["user_id"], symbol=stock["symbol"])

        # Add transaction into history, outgoing transactions are negative
        db.execute("INSERT INTO history (symbol, shares, price, total, id) VALUES (:symbol, :shares, :price, :total, :_id)",
                   symbol=stock["symbol"], shares=-shares, price=stock["price"], total=stock["price"]*shares, _id=session["user_id"])

        # If no shares of stock are owned, delete stock data from portfolio
        if holdings[0]["shares"] == shares:
            db.execute("DELETE FROM portfolio WHERE id=:_id AND symbol=:symbol", _id=session["user_id"], symbol=stock["symbol"])

        # Update user's funds
        db.execute("UPDATE users SET cash= cash+:revenue WHERE id=:_id", revenue=stock["price"]*shares, _id=session["user_id"])

        return redirect("/")

    else:

        # Grab list of stocks
        stocks = db.execute("SELECT symbol FROM portfolio WHERE id=:_id", _id=session["user_id"])

        return render_template("sell.html", stocks=stocks)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    history = db.execute("SELECT symbol, shares, price, total, date_time FROM history WHERE id=:_id",
                         _id=session["user_id"])

    # Format price into USD
    for stock in history:
        stock["price"] = usd(stock["price"])
        stock["total"] = usd(stock["total"])

    return render_template("history.html", history=history)


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


def errorhandler(e):
    """Handle error"""
    return apology(e.name, e.code)


# listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

"""Notes & Resources"""
"""
[1] Client error status code (apology function default is 400)
        https://en.wikipedia.org/wiki/List_of_HTTP_status_codes
[2] Insert username and hash into database, and provide that info in an array
        https://www.sqlite.org/lang_expr.html
[3] Hash password
        Walkthrough states to use pwd_context.encrypt. Yet there is already a security
        feature imported from werkzeug.security.
        https://passlib.readthedocs.io/en/1.6.5/new_app_quickstart.html
        NOTE: db.execute returns a list of dictionaries; [{key,value},{key,value},...]
        CORRECTION: Flask debugger states that pwd_context.ecrypt is depricated, use
                    pwd_context.hash instead. Another hash checker would have to be selected
                    to check the hash produced by this method.
[4] Keep user logged in during session
        https://pythonhosted.org/Flask-Session/
[5] Redirect user to another webpage
        http://flask.pocoo.org/docs/0.12/quickstart/#url-building
        http://flask.pocoo.org/docs/0.12/api/
[6] Redirect status code (default is 302)
        https://en.wikipedia.org/wiki/List_of_HTTP_status_codes
        https://stackoverflow.com/questions/14343812/redirecting-to-url-in-flask
[7] Partial explanation as to why one would use redirect vs. render_template
        https://stackoverflow.com/questions/21668481/difference-between-render-template-and-redirect
[8] Render html template
        http://flask.pocoo.org/docs/1.0/quickstart/
[9] helpers.py does not provide a dictionary with three keys as stated. Rather, it only returns keys
    for price and symbol. The following snipet of code starting from line 72 demonstrates this:

    # Return stock's name (as a str), price (as a float), and (uppercased) symbol (as a str)
    return {
        "price": price,
        "symbol": symbol.upper()
    }

[10] "Easier to ask for forgivenes than for permision"
        https://stackoverflow.com/questions/3501382/checking-whether-a-variable-is-an-integer-or-not
        https://docs.python.org/3/tutorial/errors.html
[11] Logical operation AND
        https://www.py4e.com/trinket3/15-database.html
"""