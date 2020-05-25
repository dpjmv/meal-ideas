from flask import Flask, render_template, request, session, redirect, jsonify
from functools import wraps
from config import params
import os, sqlite3, unidecode, json, random

jinja_params =  {
    "path": params["path"],
}

app = Flask(__name__, static_url_path="/static")
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.secret_key = os.urandom(16)

return_template = {
    "msg": "some info about what happend, is ok if everything went well",
    "status": "status code, 0 if ok, see specific method for details about error codes",
    "data": "array or object, core of the response, can be empty if an error occured"
}


def error(msg, code, http_code=400):
    return jsonify({
        "msg": msg,
        "code": code,
        "data": None
    }), http_code


def respond(data):
    return jsonify({
        "msg": "ok",
        "code": 0,
        "data": data
    }), 200


def template(*args, **kwargs):
    return render_template(*args, **kwargs, params=params)


def db_cursor():
    return sqlite3.connect(params["db_path"], isolation_level=None).cursor()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("is_logged_in"):
            return redirect(params["path"] + "/login")
        return f(*args, **kwargs)
    return decorated_function


@app.route("/")
@login_required
def index():
    return template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return template("login.html")
    elif request.method == "POST":
        if request.form.get("password") == params["password"]:
            session["is_logged_in"] = True
            return redirect(params["path"] + "/")
        else:
            return template("login.html", login_failed=True)


@app.route("/api/meals/<int:id>", methods=["GET", "DELETE"])
@login_required
def meal(id):
    if request.method == "GET":
        """ Returns the meal with the given id
        returns:
            id               -> id of the meal
            title            -> title of the meal
            description      -> description of the meal
            meal_entry       -> 0: before, 1: main course, 2: dessert
            meal_time        -> -1: any, 0: lunch, 1: dinner
            season           -> -1: any, 0: spring, 1: summer, 2: autumn, 3: winter
            preparation_time -> time it took to prep, excludes cooking time
            cook_time        -> cooking time
            ingredients      -> array of ids of the ingredients of the meal
        error:
            1 -> resource does not exist
        """
        cur = db_cursor()
        meal = cur.execute("SELECT * FROM meals WHERE id=?", [id]).fetchall()
        if not meal:
            return error("Resource does not exist", 1)

        meal = meal[0]

        ingredients = cur.execute("SELECT id FROM ingredients INNER JOIN meal_ingredients \
                                   ON ingredients.id=meal_ingredients.ingredient_id WHERE meal_id=?",
                                  [id]).fetchall()
        ingredients = [x[0] for x in ingredients]

        return respond({
            "id": meal[0],
            "title": meal[1],
            "description": meal[2],
            "meal_entry": meal[3],
            "meal_time": meal[4],
            "season": meal[5],
            "preparation_time": meal[6],
            "cook_time": meal[7],
            "ingredients": ingredients
        })


    elif request.method == "DELETE":
        """ Deletes the meal with the given id
        Does not return an error if the meal doesn't exist
        """
        db_cursor().execute("DELETE FROM meals WHERE id=?", [id])
        db_cursor().execute("DELETE FROM meal_ingredients WHERE meal_id=?", [id])
        return respond(None)


@app.route("/api/meals", methods=["GET", "POST"])
@login_required
def meals():
    if request.method == "GET":
        """ Search for meals
        parameters:
            args:
                mode                 (optional, default: search) -> search: search for meals using parameters
                                                                    random: get a random meal with given parameters
                title                        (optional)                                            
                meal_entry           (int)   (optional)              -> 0: before, 1: main course, 2: dessert
                meal_time            (int)   (optional)              -> -1: any, 0: lunch, 1: dinner
                season               (int)   (optional)              -> -1: any, 0: spring, 1: summer, 2: autumn, 3: winter
                preparation_time_max (int)   (optional)              -> maximum time to prep, 0 will be considered as any
                cook_time_max        (int)   (optional)              -> maximum cooking time, 0 will be considered as any
                total_time_max       (int)   (optional)              -> maximum time for preparation_time + cook_time,
                                                                        0 will be considered as any
                ingredients          (array) (optional)              -> array of ids of the ingredients of the meal
        returns:
            search mode:
                an array of meal objects matching the query
            random mode:
                a single meal object matching the query
        errors:
            3  -> Invalid meal entry
            4  -> Invalid meal time
            5  -> Invalid season
            6  -> Invalid maximum preparation time, should be a positive number
            7  -> Invalid maximum cook time, should be a positive number
            8  -> Invalid maximum total time, should be a positive number
            9  -> Malformed request, couldn't parse parameters
            10 -> Ingredient ids must be integers
        """
        # Parse request
        mode = request.args.get("mode")
        if not mode:
            mode == "search"

        data = {
            "title": request.args.get("title"),
            "meal_entry": request.args.get("meal_entry"),
            "meal_time": request.args.get("meal_time"),
            "season": request.args.get("season"),
            "preparation_time_max": request.args.get("preparation_time_max"),
            "cook_time_max": request.args.get("cook_time_max"),
            "total_time_max": request.args.get("total_time_max"),
            "ingredients": request.args.get("ingredients")
        }
        
        # Build SQL query
        query_base = "SELECT id, title, description, meal_entry, meal_time, season, preparation_time, cook_time FROM meals "
        query_conditions = []
        arguments = []

        if data["title"]:
            query_conditions.append(" title LIKE ? ")
            arguments.append("%" + "%".join(unidecode.unidecode(data["title"]).split()) + "%")
        
        if data["meal_entry"]:
            try:
                data["meal_entry"] = int(data["meal_entry"])
            except ValueError:
                return error("Invalid meal entry. Should be 0, 1 or 2.", 3)

            if not data["meal_entry"] in {0, 1, 2}:
                return error("Invalid meal entry. Should be 0, 1 or 2.", 3)

            query_conditions.append(" meal_entry = ? ")
            arguments.append(data["meal_entry"])

        if data["meal_time"]:
            try:
                data["meal_time"] = int(data["meal_time"])
            except ValueError:
                return error("Invalid meal time. Should be -1, 0 or 1.", 4)

            if not data["meal_time"] in {-1, 0, 1}:
                return error("Invalid meal time. Should be -1, 0 or 1.", 4)

            query_conditions.append(" meal_time = ? ")
            arguments.append(data["meal_time"])

        if data["season"]:
            try:
                data["season"] = int(data["season"])
            except ValueError:
                return error("Invalid season. Should be -1, 0, 1, 2 or 3.", 5)
            
            if not data["season"] in {-1 ,0, 1, 2, 3}:
                return error("Invalid season. Should be -1, 0, 1, 2 or 3.", 5)
            
            query_conditions.append(" season = ? ")
            arguments.append(data["season"])

        if data["preparation_time_max"]:
            try:
                data["preparation_time_max"] = int(data["preparation_time_max"])
            except ValueError:
                return error("Invalid maximum preparation time, should be a positive number.", 6)
            
            if data["preparation_time_max"] < 0:
                return error("Invalid maximum preparation time, should be a positive number.", 6)
            
            query_conditions.append(" preparation_time <= ? ")
            arguments.append(data["preparation_time_max"])

        if data["cook_time_max"]:
            try:
                data["cook_time_max"] = int(data["cook_time_max"])
            except ValueError:
                return error("Invalid maximum cook time, should be a positive number", 7)

            if data["cook_time_max"] < 0:
                return error("Invalid maximum cook time, should be a positive number", 7)

            query_conditions.append(" cook_time <= ? ")
            arguments.append(data["cook_time_max"])

        if data["total_time_max"]:
            try:
                data["total_time_max"] = int(data["total_time_max"])
            except ValueError:
                return error("Invalid maximum total time, should be a positive number", 8)

            if data["total_time_max"] < 0:
                return error("Invalid maximum total time, should be a positive number", 8)

            query_conditions.append(" (cook_time + preparation_time) <= ? ")
            arguments.append(data["total_time_max"])


        if data["ingredients"]:
            try:
                data["ingredients"] = json.loads(data["ingredients"])
            except json.JSONDecodeError:
                return error("Malformed request, couldn't parse parameters.", 9)
            
            for ingredient in data["ingredients"]:                
                query_conditions.append(" ? IN (SELECT ingredient_id FROM meal_ingredients WHERE meal_id = meals.id) ")
                try:
                    arguments.append(int(ingredient))
                except ValueError:
                    return error("Ingredient ids must be integers.", 10)

        # Query database
        cur = db_cursor()
        query_ingredients = "SELECT ingredient_id FROM meal_ingredients WHERE meal_id = ?"

        query_final = query_base 
        if query_conditions:
            query_final += " WHERE " + " AND ".join(query_conditions)
        
        result = cur.execute(query_final, arguments).fetchall()

        #  Format response and send
        response = [{
            "id": meal[0],
            "title": meal[1],
            "description": meal[2],
            "meal_entry": meal[3],
            "meal_time": meal[4],
            "season": meal[5],
            "preparation_time": meal[6],
            "cook_time": meal[7],
            "ingredients": [x[0] for x in cur.execute(query_ingredients, [meal[0]]).fetchall()]
        } for meal in result]

        if mode == "random":
            response = random.choice(response)

        return respond(response)

    
    elif request.method == "POST":
        """ Add a meal to the database
        parameters:
            form:
                title                                            -> title of the meal
                description              (optional)              -> description of the meal
                meal_entry       (int)   (optional, default: 1)  -> 0: before, 1: main course, 2: dessert
                meal_time        (int)   (optional, default: -1) -> -1: any, 0: lunch, 1: dinner
                season           (int)   (optional, default: -1) -> -1: any, 0: spring, 1: summer, 2: autumn, 3: winter
                preparation_time (int)   (optional)              -> time it took to prep, excludes cooking time
                cook_time        (int)   (optional)              -> cooking time
                ingredients      (array) (optional)              -> array of ids of the ingredients of the meal
        returns:
            meal_id -> id of the newly created meal
        errors:
            1 -> Malformed request, missing parameter title
            2 -> Meal already with given title already exists
            3 -> Invalid meal entry
            4 -> Invalid meal time
            5 -> Invalid season
            6 -> Invalid preparation time, should be positive
            7 -> Invalid cook time, should be positive
            8 -> Malformed request, couldn't parse parameters
            9 -> Ingredient ids must be integers
        """
        # Retrieve input
        data = {
            "title": request.form.get("title"),
            "description": request.form.get("description"),
            "meal_entry": request.form.get("meal_entry"),
            "meal_time": request.form.get("meal_time"),
            "season": request.form.get("season"),
            "preparation_time": request.form.get("preparation_time"),
            "cook_time": request.form.get("cook_time"),
            "ingredients": request.form.get("ingredients")
        }

        if not data["title"]:
            return error("Malformed request, missing parameter title.", 1)
        data["title"] = unidecode.unidecode(data["title"])
        
        if not data["description"]:
            data["description"] = ""
        data["description"] = unidecode.unidecode(data["description"])
        
        if not data["meal_entry"]:
            data["meal_entry"] = 1
        else:
            try:
                data["meal_entry"] = int(data["meal_entry"])
            except ValueError:
                return error("Invalid meal entry. Should be 0, 1 or 2.", 3)

            if not data["meal_entry"] in {0, 1, 2}:
                return error("Invalid meal entry. Should be 0, 1 or 2.", 3)

        if not data["meal_time"]:
            data["meal_time"] = -1
        else:
            try:
                data["meal_time"] = int(data["meal_time"])
            except ValueError:
                return error("Invalid meal time. Should be -1, 0 or 1.", 4)

            if not data["meal_time"] in {-1, 0, 1}:
                return error("Invalid meal time. Should be -1, 0 or 1.", 4)

        if not data["season"]:
            data["season"] = -1
        else:
            try:
                data["season"] = int(data["season"])
            except ValueError:
                return error("Invalid season. Should be -1, 0, 1, 2 or 3.", 5)

            if not data["season"] in {-1 ,0, 1, 2, 3}:
                return error("Invalid season. Should be -1, 0, 1, 2 or 3.", 5)

        if not data["preparation_time"]:
            data["preparation_time"] = None
        else:
            try:
                data["preparation_time"] = int(data["preparation_time"])
            except ValueError:
                return error("Invalid preparation time, should be a positive number.", 6)

            if data["preparation_time"] < 0:
                return error("Invalid preparation time, should be a positive number.", 6)

        if not data["cook_time"]:
            data["cook_time"] = None
        else:
            try:
                data["cook_time"] = int(data["cook_time"])
            except ValueError:
                return error("Invalid cook time, should be a positive number", 7)

            if data["cook_time"] < 0:
                return error("Invalid cook time, should be a positive number", 7)

        if not data["ingredients"]:
            data["ingredients"] = []
        else:
            try:
                data["ingredients"] = json.loads(data["ingredients"])
            except json.JSONDecodeError:
                return error("Malformed request, couldn't parse parameters.", 8)
            
            for ingredient in data["ingredients"]:
                try:
                    int(ingredient)
                except ValueError:
                    return error("Ingredient ids must be integers.", 9)

        # Insert into database
        cur = db_cursor()
        is_existing = cur.execute("SELECT id FROM meals WHERE title=?", [data["title"]]).fetchall()
        if is_existing:
            return error("Meal with given title already exists.", 2)
        
        cur.execute("INSERT INTO meals (title, description, meal_entry, meal_time, season, preparation_time, cook_time) \
                     VALUES (?,?,?,?,?,?,?)",
                    [data["title"], data["description"], data["meal_entry"], data["meal_time"],
                     data["season"], data["preparation_time"], data["cook_time"]])

        meal_id = cur.execute("SELECT id FROM meals WHERE title=?", [data["title"]]).fetchall()[0][0]

        for ingredient_id in data["ingredients"]:
            cur.execute("INSERT INTO meal_ingredients (meal_id, ingredient_id) VALUES (?,?)",
                        [meal_id, ingredient_id])

        return respond({
            "meal_id": meal_id
        })



@app.route("/api/ingredients", methods=["GET", "POST"])
@login_required
def ingredients():
    if request.method == "GET":
        """ Get ingredients given some parameters
        parameters:
            args:
                mode (optional, default search) -> search: provide a query string and get matching results,
                                                   many: provide a list of ingredient ids and get 
                                                         the corresponding ingredient objects, no error is returned
                                                         if an invalid id is provided
                q -> search mode: a string, 
                     many mode: an JSON array of ingredient ids (less than a 100 long)  
        returns:
            an array of ingredient objects corresponding to the query
        errors:
            1 -> missing parameter 'q'
            2 -> invalid value for 'mode' 
            3 -> malformed request, couldn't parse it
        """
        cur = db_cursor()

        mode = request.args.get("mode")
        if not mode:
            mode = "search"

        if request.args.get("q"):
            if mode == "search":
                query = "%" + unidecode.unidecode(request.args.get("q")) + "%"
                response_data = cur.execute("SELECT * FROM ingredients WHERE name LIKE ?", 
                                            [query]).fetchall()

            elif mode == "many":
                try:
                    query = json.loads(request.args.get("q"))
                except json.JSONDecodeError:
                    return error("Malformed request, couldn't parse parameters.", 3)

                args_serialized = ",".join(["?"] * len(query))
                response_data = cur.execute("SELECT * FROM ingredients WHERE id IN ("+args_serialized+")",
                                            query).fetchall()
            else:
                return error("Malformed request, invalid value for parameter mode.", 2)
        else:
            return error("Malformed request, parameter q for query is required.", 1)

        return respond([{"id": ingredient[0], "name": ingredient[1]} for ingredient in response_data])


    elif request.method == "POST":
        """ Post a json to create an ingredient
        parameters:
            form:
                name -> name of the new ingredient
        returns:
            ingredient_id -> the id of the added ingredient
        errors:
            1 -> missing parameter 'name'
            2 -> ingredient exists
        """
        if request.form.get("name"):
            ingredient_name = unidecode.unidecode(request.form.get("name")).lower()
        else:
            return error("Malformed request, parameter name is required.", 1)

        cur = db_cursor()

        is_existing = cur.execute("SELECT id FROM ingredients WHERE name=?",  [ingredient_name]).fetchall()
        if not is_existing:
            cur.execute("INSERT INTO ingredients (name) VALUES(?)", [ingredient_name])
            ingredient_id = cur.execute("SELECT id FROM ingredients WHERE name=?",  [ingredient_name]).fetchall()[0][0]
            return respond({
                    "ingredient_id": ingredient_id 
            })
        else:
            return error("Ingredient exists.", 2)
    

@app.route("/api/ingredients/<int:id>", methods=["GET", "DELETE"])
@login_required
def ingredient(id):
    if request.method == "GET":
        """ Returns the ingredient with the given id
        returns:
            id
            name
        error:
            1 -> resource does not exist
        """
        ingredient = db_cursor().execute("SELECT * FROM ingredients WHERE id=?", [id]).fetchall()
        if not ingredient:
            return error("Resource does not exist", 1)

        return respond({
            "id": ingredient[0][0],
            "name": ingredient[0][1]
        })


    if request.method == "DELETE":
        """ Deletes the ingredient with the given id
        Does not return an error if the ingredient doesn't exist
        Deletes the ingredient from every meal where it is used
        """
        cur = db_cursor()
        cur.execute("DELETE FROM ingredients WHERE id=?", [id])
        cur.execute("DELETE FROM meal_ingredients WHERE meal_id=?", [id])
        return respond(None)


@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    session["is_logged_in"] = False
    return redirect(params["path"] + "/login")