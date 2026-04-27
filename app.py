from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    Response,
)
import pymysql
from config import Config
import csv
from io import StringIO


app = Flask(__name__)
app.secret_key = 'dev-secret-key-for-assignment'
app.config.from_object(Config)


def get_db_connection():
    return pymysql.connect(
        host=app.config["MYSQL_HOST"],
        user=app.config["MYSQL_USER"],
        password=app.config["MYSQL_PASSWORD"],
        database=app.config["MYSQL_DB"],
        cursorclass=pymysql.cursors.DictCursor,
    )


# Dashboard route
@app.route("/")
def dashboard():
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Get total counts
            cur.execute("SELECT COUNT(*) as total FROM film")
            total_films = cur.fetchone()["total"]

            cur.execute("SELECT COUNT(*) as total FROM actor")
            total_actors = cur.fetchone()["total"]

            cur.execute("SELECT COUNT(*) as total FROM customer")
            total_customers = cur.fetchone()["total"]

            cur.execute(
                "SELECT COUNT(*) as total FROM rental WHERE return_date IS NULL"
            )
            active_rentals = cur.fetchone()["total"]

            # Get revenue statistics
            cur.execute(
                """
                SELECT SUM(amount) as total_revenue,
                       AVG(amount) as avg_rental_price,
                       COUNT(*) as total_transactions
                FROM payment
                WHERE payment_date >= DATE_SUB(NOW(), INTERVAL 30 DAY)
            """
            )
            revenue_stats = cur.fetchone()

            # Get recent rentals
            cur.execute(
                """
                SELECT r.rental_id, f.title, c.first_name, c.last_name, r.rental_date
                FROM rental r
                JOIN inventory i ON r.inventory_id = i.inventory_id
                JOIN film f ON i.film_id = f.film_id
                JOIN customer c ON r.customer_id = c.customer_id
                ORDER BY r.rental_date DESC
                LIMIT 10
            """
            )
            recent_rentals = cur.fetchall()

            # Get popular films
            cur.execute(
                """
                SELECT f.title, COUNT(r.rental_id) as rental_count
                FROM film f
                JOIN inventory i ON f.film_id = i.film_id
                JOIN rental r ON i.inventory_id = r.inventory_id
                GROUP BY f.film_id, f.title
                ORDER BY rental_count DESC
                LIMIT 10
            """
            )
            popular_films = cur.fetchall()

            # Get store statistics
            cur.execute(
                """
                SELECT s.store_id, a.address, a.district, ci.city, co.country,
                       (SELECT COUNT(*) FROM customer c WHERE c.store_id = s.store_id) as customer_count,
                       (SELECT COUNT(*) FROM inventory i WHERE i.store_id = s.store_id) as inventory_count
                FROM store s
                JOIN address a ON s.address_id = a.address_id
                JOIN city ci ON a.city_id = ci.city_id
                JOIN country co ON ci.country_id = co.country_id
            """
            )
            store_stats = cur.fetchall()

        conn.close()
        return render_template(
            "dashboard.html",
            total_films=total_films,
            total_actors=total_actors,
            total_customers=total_customers,
            active_rentals=active_rentals,
            revenue_stats=revenue_stats,
            recent_rentals=recent_rentals,
            popular_films=popular_films,
            store_stats=store_stats,
        )
    except Exception as e:
        flash(f"Error loading dashboard: {str(e)}", "error")
        return render_template(
            "dashboard.html",
            total_films=0,
            total_actors=0,
            total_customers=0,
            active_rentals=0,
            revenue_stats={
                "total_revenue": 0,
                "avg_rental_price": 0,
                "total_transactions": 0,
            },
            recent_rentals=[],
            popular_films=[],
            store_stats=[],
        )


# Films Routes with Search and Pagination
@app.route("/films")
def films():
    page = request.args.get("page", 1, type=int)
    per_page = 20
    search = request.args.get("search", "")
    category = request.args.get("category", "")
    rating = request.args.get("rating", "")
    min_year = request.args.get("min_year", "")
    max_year = request.args.get("max_year", "")

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Build query with filters
            query = """
                SELECT f.film_id, f.title, f.release_year, f.rental_rate,
                       f.length, f.rating, c.name as category,
                       COUNT(r.rental_id) as rental_count,
                       l.name as language_name
                FROM film f
                LEFT JOIN film_category fc ON f.film_id = fc.film_id
                LEFT JOIN category c ON fc.category_id = c.category_id
                LEFT JOIN inventory i ON f.film_id = i.film_id
                LEFT JOIN rental r ON i.inventory_id = r.inventory_id
                LEFT JOIN language l ON f.language_id = l.language_id
            """
            where_conditions = []
            params = []

            if search:
                where_conditions.append("(f.title LIKE %s OR f.description LIKE %s)")
                params.extend([f"%{search}%", f"%{search}%"])

            if category:
                where_conditions.append("c.name = %s")
                params.append(category)

            if rating:
                where_conditions.append("f.rating = %s")
                params.append(rating)

            if min_year:
                where_conditions.append("f.release_year >= %s")
                params.append(min_year)

            if max_year:
                where_conditions.append("f.release_year <= %s")
                params.append(max_year)

            if where_conditions:
                query += " WHERE " + " AND ".join(where_conditions)

            query += " GROUP BY f.film_id, f.title, f.release_year, f.rental_rate, f.length, f.rating, c.name, l.name"
            query += " ORDER BY f.title"

            # Get total count for pagination
            count_query = "SELECT COUNT(DISTINCT f.film_id) as total FROM film f"
            count_query += " LEFT JOIN film_category fc ON f.film_id = fc.film_id"
            count_query += " LEFT JOIN category c ON fc.category_id = c.category_id"

            if where_conditions:
                count_query += " WHERE " + " AND ".join(where_conditions)

            cur.execute(count_query, params)
            total = cur.fetchone()["total"]

            # Apply pagination
            query += " LIMIT %s OFFSET %s"
            params.extend([per_page, (page - 1) * per_page])

            cur.execute(query, params)
            films = cur.fetchall()

            # Get categories for filter dropdown
            cur.execute("SELECT DISTINCT name FROM category ORDER BY name")
            categories = [cat["name"] for cat in cur.fetchall()]

            # Get ratings for filter dropdown
            cur.execute(
                "SELECT DISTINCT rating FROM film WHERE rating IS NOT NULL ORDER BY rating"
            )
            ratings = [rating["rating"] for rating in cur.fetchall()]

            # Get years range for filter
            cur.execute(
                "SELECT MIN(release_year) as min_year, MAX(release_year) as max_year FROM film"
            )
            year_range = cur.fetchone()

        conn.close()

        total_pages = (total + per_page - 1) // per_page

        return render_template(
            "films.html",
            films=films,
            categories=categories,
            ratings=ratings,
            year_range=year_range,
            search=search,
            selected_category=category,
            selected_rating=rating,
            min_year=min_year,
            max_year=max_year,
            page=page,
            total_pages=total_pages,
            total=total,
        )
    except Exception as e:
        flash(f"Error fetching films: {str(e)}", "error")
        return render_template(
            "films.html",
            films=[],
            categories=[],
            ratings=[],
            year_range={"min_year": 1900, "max_year": 2100},
            search=search,
            selected_category=category,
            selected_rating=rating,
            min_year=min_year,
            max_year=max_year,
            page=1,
            total_pages=1,
            total=0,
        )


@app.route("/films/add", methods=["GET", "POST"])
def add_film():
    if request.method == "POST":
        try:
            # Extract form data
            title = request.form["title"]
            description = request.form["description"]
            release_year = request.form["release_year"] or None
            language_id = request.form["language_id"]
            rental_duration = request.form["rental_duration"] or 3
            rental_rate = request.form["rental_rate"] or 4.99
            length = request.form["length"] or None
            replacement_cost = request.form["replacement_cost"] or 19.99
            rating = request.form["rating"]
            special_features = request.form.get("special_features", "")

            # Get selected actors and category
            actors = request.form.getlist("actors")
            category_id = request.form.get("category_id")

            conn = get_db_connection()
            with conn.cursor() as cur:
                # Insert film
                cur.execute(
                    """
                    INSERT INTO film (title, description, release_year, language_id,
                                    rental_duration, rental_rate, length, replacement_cost,
                                    rating, special_features)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        title,
                        description,
                        release_year,
                        language_id,
                        rental_duration,
                        rental_rate,
                        length,
                        replacement_cost,
                        rating,
                        special_features,
                    ),
                )

                film_id = cur.lastrowid

                # Add film-category relationship
                if category_id:
                    cur.execute(
                        "INSERT INTO film_category (film_id, category_id) VALUES (%s, %s)",
                        (film_id, category_id),
                    )

                # Add film-actor relationships
                for actor_id in actors:
                    cur.execute(
                        "INSERT INTO film_actor (film_id, actor_id) VALUES (%s, %s)",
                        (film_id, actor_id),
                    )

                conn.commit()
            conn.close()
            flash("Film added successfully!", "success")
            return redirect(url_for("films"))

        except Exception as e:
            flash(f"Error adding film: {str(e)}", "error")

    # Get data for dropdowns
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT language_id, name FROM language")
            languages = cur.fetchall()

            cur.execute("SELECT category_id, name FROM category ORDER BY name")
            categories = cur.fetchall()

            cur.execute(
                "SELECT actor_id, first_name, last_name FROM actor ORDER BY first_name, last_name"
            )
            actors = cur.fetchall()
        conn.close()
    except Exception as e:
        flash(f"Error loading form data: {str(e)}", "error")
        languages = []
        categories = []
        actors = []

    return render_template(
        "film_form.html",
        film=None,
        languages=languages,
        categories=categories,
        actors=actors,
    )


@app.route("/films/edit/<int:film_id>", methods=["GET", "POST"])
def edit_film(film_id):
    if request.method == "POST":
        try:
            title = request.form["title"]
            description = request.form["description"]
            release_year = request.form["release_year"] or None
            language_id = request.form["language_id"]
            rental_duration = request.form["rental_duration"] or 3
            rental_rate = request.form["rental_rate"] or 4.99
            length = request.form["length"] or None
            replacement_cost = request.form["replacement_cost"] or 19.99
            rating = request.form["rating"]
            special_features = request.form.get("special_features", "")

            # Get selected actors and category
            actors = request.form.getlist("actors")
            category_id = request.form.get("category_id")

            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE film
                    SET title=%s, description=%s, release_year=%s, language_id=%s,
                        rental_duration=%s, rental_rate=%s, length=%s,
                        replacement_cost=%s, rating=%s, special_features=%s
                    WHERE film_id=%s
                """,
                    (
                        title,
                        description,
                        release_year,
                        language_id,
                        rental_duration,
                        rental_rate,
                        length,
                        replacement_cost,
                        rating,
                        special_features,
                        film_id,
                    ),
                )

                # Update film-category relationship
                cur.execute("DELETE FROM film_category WHERE film_id = %s", (film_id,))
                if category_id:
                    cur.execute(
                        "INSERT INTO film_category (film_id, category_id) VALUES (%s, %s)",
                        (film_id, category_id),
                    )

                # Update film-actor relationships
                cur.execute("DELETE FROM film_actor WHERE film_id = %s", (film_id,))
                for actor_id in actors:
                    cur.execute(
                        "INSERT INTO film_actor (film_id, actor_id) VALUES (%s, %s)",
                        (film_id, actor_id),
                    )

                conn.commit()
            conn.close()
            flash("Film updated successfully!", "success")
            return redirect(url_for("films"))

        except Exception as e:
            flash(f"Error updating film: {str(e)}", "error")

    # Get film data
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM film WHERE film_id = %s", (film_id,))
            film = cur.fetchone()

            if not film:
                flash("Film not found!", "error")
                return redirect(url_for("films"))

            # Get current category
            cur.execute(
                "SELECT category_id FROM film_category WHERE film_id = %s", (film_id,)
            )
            category_result = cur.fetchone()
            if category_result:
                film["category_id"] = category_result["category_id"]

            # Get current actors
            cur.execute(
                """
                SELECT a.actor_id
                FROM actor a
                JOIN film_actor fa ON a.actor_id = fa.actor_id
                WHERE fa.film_id = %s
            """,
                (film_id,),
            )
            film_actors = cur.fetchall()
            film["actors"] = [actor["actor_id"] for actor in film_actors]

        # Get data for dropdowns
        with conn.cursor() as cur:
            cur.execute("SELECT language_id, name FROM language")
            languages = cur.fetchall()

            cur.execute("SELECT category_id, name FROM category ORDER BY name")
            categories = cur.fetchall()

            cur.execute(
                "SELECT actor_id, first_name, last_name FROM actor ORDER BY first_name, last_name"
            )
            actors = cur.fetchall()
        conn.close()

        return render_template(
            "film_form.html",
            film=film,
            languages=languages,
            categories=categories,
            actors=actors,
        )
    except Exception as e:
        if "conn" in locals():
            conn.close()
        flash(f"Error loading film: {str(e)}", "error")
        return redirect(url_for("films"))


@app.route("/films/delete/<int:film_id>")
def delete_film(film_id):
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Check if film exists in inventory or rentals
            cur.execute(
                "SELECT COUNT(*) as count FROM inventory WHERE film_id = %s", (film_id,)
            )
            inventory_count = cur.fetchone()["count"]

            if inventory_count > 0:
                flash(
                    "Cannot delete film: It exists in inventory or has rental history.",
                    "error",
                )
                return redirect(url_for("films"))

            # Delete film relationships first
            cur.execute("DELETE FROM film_actor WHERE film_id = %s", (film_id,))
            cur.execute("DELETE FROM film_category WHERE film_id = %s", (film_id,))

            # Delete the film
            cur.execute("DELETE FROM film WHERE film_id = %s", (film_id,))
            conn.commit()
        conn.close()
        flash("Film deleted successfully!", "success")
    except Exception as e:
        flash(f"Error deleting film: {str(e)}", "error")

    return redirect(url_for("films"))


@app.route("/films/<int:film_id>")
def film_detail(film_id):
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Get film details
            cur.execute(
                """
                SELECT f.*, l.name as language_name, c.name as category, c.category_id
                FROM film f
                LEFT JOIN language l ON f.language_id = l.language_id
                LEFT JOIN film_category fc ON f.film_id = fc.film_id
                LEFT JOIN category c ON fc.category_id = c.category_id
                WHERE f.film_id = %s
            """,
                (film_id,),
            )
            film = cur.fetchone()

            if not film:
                flash("Film not found!", "error")
                return redirect(url_for("films"))

            # Get actors
            cur.execute(
                """
                SELECT a.actor_id, a.first_name, a.last_name
                FROM actor a
                JOIN film_actor fa ON a.actor_id = fa.actor_id
                WHERE fa.film_id = %s
                ORDER BY a.first_name, a.last_name
            """,
                (film_id,),
            )
            actors = cur.fetchall()

            # Get inventory count
            cur.execute(
                "SELECT COUNT(*) as inventory_count FROM inventory WHERE film_id = %s",
                (film_id,),
            )
            inventory_count = cur.fetchone()["inventory_count"]

            # Get rental statistics
            cur.execute(
                """
                SELECT COUNT(*) as total_rentals,
                       AVG(DATEDIFF(return_date, rental_date)) as avg_rental_days
                FROM rental r
                JOIN inventory i ON r.inventory_id = i.inventory_id
                WHERE i.film_id = %s AND r.return_date IS NOT NULL
            """,
                (film_id,),
            )
            rental_stats = cur.fetchone()

            # Get revenue from this film
            cur.execute(
                """
                SELECT SUM(p.amount) as total_revenue
                FROM payment p
                JOIN rental r ON p.rental_id = r.rental_id
                JOIN inventory i ON r.inventory_id = i.inventory_id
                WHERE i.film_id = %s
            """,
                (film_id,),
            )
            revenue = cur.fetchone()

        conn.close()
        return render_template(
            "film_detail.html",
            film=film,
            actors=actors,
            inventory_count=inventory_count,
            rental_stats=rental_stats,
            revenue=revenue,
        )
    except Exception as e:
        flash(f"Error loading film details: {str(e)}", "error")
        return redirect(url_for("films"))


# Export films to CSV
@app.route("/films/export")
def export_films():
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT f.film_id, f.title, f.description, f.release_year,
                       f.rental_rate, f.length, f.rating, c.name as category,
                       l.name as language, f.replacement_cost, f.rental_duration,
                       f.special_features
                FROM film f
                LEFT JOIN film_category fc ON f.film_id = fc.film_id
                LEFT JOIN category c ON fc.category_id = c.category_id
                LEFT JOIN language l ON f.language_id = l.language_id
                ORDER BY f.title
            """
            )
            films = cur.fetchall()
        conn.close()

        # Create CSV
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "ID",
                "Title",
                "Description",
                "Release Year",
                "Rental Rate",
                "Length",
                "Rating",
                "Category",
                "Language",
                "Replacement Cost",
                "Rental Duration",
                "Special Features",
            ]
        )

        for film in films:
            writer.writerow(
                [
                    film["film_id"],
                    film["title"],
                    film["description"] or "",
                    film["release_year"] or "",
                    film["rental_rate"],
                    film["length"] or "",
                    film["rating"] or "",
                    film["category"] or "",
                    film["language"] or "",
                    film["replacement_cost"],
                    film["rental_duration"],
                    film["special_features"] or "",
                ]
            )

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=films_export.csv"},
        )
    except Exception as e:
        flash(f"Error exporting films: {str(e)}", "error")
        return redirect(url_for("films"))


# Enhanced Actors Routes
@app.route("/actors")
def actors():
    page = request.args.get("page", 1, type=int)
    per_page = 20
    search = request.args.get("search", "")
    sort = request.args.get("sort", "name_asc")

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Build query
            query = """
                SELECT a.actor_id, a.first_name, a.last_name,
                       DATE_FORMAT(a.last_update, '%%Y-%%m-%%d %%H:%%i:%%s') as last_update,
                       COUNT(fa.film_id) as film_count
                FROM actor a
                LEFT JOIN film_actor fa ON a.actor_id = fa.actor_id
            """
            params = []

            if search:
                query += " WHERE (a.first_name LIKE %s OR a.last_name LIKE %s)"
                params.extend([f"%{search}%", f"%{search}%"])

            query += " GROUP BY a.actor_id, a.first_name, a.last_name, a.last_update"

            # Apply sorting
            if sort == "name_asc":
                query += " ORDER BY a.first_name, a.last_name"
            elif sort == "name_desc":
                query += " ORDER BY a.first_name DESC, a.last_name DESC"
            elif sort == "recent":
                query += " ORDER BY a.last_update DESC"
            elif sort == "film_count":
                query += " ORDER BY film_count DESC"
            else:
                query += " ORDER BY a.first_name, a.last_name"

            # Get total count
            count_query = "SELECT COUNT(DISTINCT a.actor_id) as total FROM actor a"
            if search:
                count_query += " WHERE (a.first_name LIKE %s OR a.last_name LIKE %s)"

            cur.execute(count_query, params)
            total = cur.fetchone()["total"]

            # Apply pagination
            query += " LIMIT %s OFFSET %s"
            params.extend([per_page, (page - 1) * per_page])

            cur.execute(query, params)
            actors = cur.fetchall()

            # Get popular actors (appear in 10+ films)
            cur.execute(
                """
                SELECT a.actor_id, a.first_name, a.last_name, COUNT(fa.film_id) as film_count
                FROM actor a
                JOIN film_actor fa ON a.actor_id = fa.actor_id
                GROUP BY a.actor_id, a.first_name, a.last_name
                HAVING COUNT(fa.film_id) >= 10
                ORDER BY film_count DESC
                LIMIT 8
            """
            )
            popular_actors = cur.fetchall()

            # Get actor with most films
            cur.execute(
                """
                SELECT COUNT(fa.film_id) as film_count
                FROM actor a
                JOIN film_actor fa ON a.actor_id = fa.actor_id
                GROUP BY a.actor_id
                ORDER BY film_count DESC
                LIMIT 1
            """
            )
            most_films = cur.fetchone()
            most_films_count = most_films["film_count"] if most_films else 0

        conn.close()

        total_pages = (total + per_page - 1) // per_page

        return render_template(
            "actors.html",
            actors=actors,
            popular_actors=popular_actors,
            most_films_count=most_films_count,
            search=search,
            sort=sort,
            page=page,
            total_pages=total_pages,
            total=total,
        )
    except Exception as e:
        flash(f"Error fetching actors: {str(e)}", "error")
        # Return all required variables even in case of error
        return render_template(
            "actors.html",
            actors=[],
            popular_actors=[],
            most_films_count=0,
            search=search,
            sort=sort,
            page=1,
            total_pages=1,
            total=0,
        )


@app.route("/actors/add", methods=["POST"])
def add_actor():
    try:
        first_name = request.form["first_name"]
        last_name = request.form["last_name"]

        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO actor (first_name, last_name) VALUES (%s, %s)",
                (first_name, last_name),
            )
            conn.commit()
        conn.close()
        flash("Actor added successfully!", "success")
    except Exception as e:
        flash(f"Error adding actor: {str(e)}", "error")

    return redirect(url_for("actors"))


@app.route("/actors/edit/<int:actor_id>", methods=["POST"])
def edit_actor(actor_id):
    try:
        first_name = request.form["first_name"]
        last_name = request.form["last_name"]

        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE actor SET first_name=%s, last_name=%s WHERE actor_id=%s",
                (first_name, last_name, actor_id),
            )
            conn.commit()
        conn.close()
        flash("Actor updated successfully!", "success")
    except Exception as e:
        flash(f"Error updating actor: {str(e)}", "error")

    return redirect(url_for("actors"))


@app.route("/actors/delete/<int:actor_id>")
def delete_actor(actor_id):
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Check if actor has film relationships
            cur.execute(
                "SELECT COUNT(*) as count FROM film_actor WHERE actor_id = %s",
                (actor_id,),
            )
            film_count = cur.fetchone()["count"]

            if film_count > 0:
                flash(
                    "Cannot delete actor: Actor is associated with films. Remove film associations first.",
                    "error",
                )
                return redirect(url_for("actors"))

            cur.execute("DELETE FROM actor WHERE actor_id = %s", (actor_id,))
            conn.commit()
        conn.close()
        flash("Actor deleted successfully!", "success")
    except Exception as e:
        flash(f"Error deleting actor: {str(e)}", "error")

    return redirect(url_for("actors"))


# API route for actor details
@app.route("/api/actor/<int:actor_id>")
def get_actor_details(actor_id):
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Get actor basic info
            cur.execute("SELECT * FROM actor WHERE actor_id = %s", (actor_id,))
            actor = cur.fetchone()

            if not actor:
                return jsonify({"error": "Actor not found"}), 404

            # Get films featuring this actor
            cur.execute(
                """
                SELECT f.film_id, f.title, f.release_year, f.rating, c.name as category
                FROM film f
                JOIN film_actor fa ON f.film_id = fa.film_id
                LEFT JOIN film_category fc ON f.film_id = fc.film_id
                LEFT JOIN category c ON fc.category_id = c.category_id
                WHERE fa.actor_id = %s
                ORDER BY f.title
            """,
                (actor_id,),
            )
            films = cur.fetchall()

        conn.close()

        return jsonify({"actor": actor, "films": films})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# API Routes for film details
@app.route("/api/film/<int:film_id>")
def get_film_details(film_id):
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Get film basic info
            cur.execute(
                """
                SELECT f.*, l.name as language_name, c.name as category
                FROM film f
                LEFT JOIN language l ON f.language_id = l.language_id
                LEFT JOIN film_category fc ON f.film_id = fc.film_id
                LEFT JOIN category c ON fc.category_id = c.category_id
                WHERE f.film_id = %s
            """,
                (film_id,),
            )
            film = cur.fetchone()

            if not film:
                return jsonify({"error": "Film not found"}), 404

            # Get actors in the film
            cur.execute(
                """
                SELECT a.actor_id, a.first_name, a.last_name
                FROM actor a
                JOIN film_actor fa ON a.actor_id = fa.actor_id
                WHERE fa.film_id = %s
            """,
                (film_id,),
            )
            actors = cur.fetchall()

        conn.close()

        return jsonify({"film": film, "actors": actors})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Customers Management
@app.route("/customers")
def customers():
    page = request.args.get("page", 1, type=int)
    per_page = 20
    search = request.args.get("search", "")

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            query = """
                SELECT c.customer_id, c.first_name, c.last_name, c.email,
                       a.address, a.district, ci.city, co.country,
                       c.active, c.create_date,
                       (SELECT COUNT(*) FROM rental r WHERE r.customer_id = c.customer_id) as rental_count
                FROM customer c
                JOIN address a ON c.address_id = a.address_id
                JOIN city ci ON a.city_id = ci.city_id
                JOIN country co ON ci.country_id = co.country_id
            """
            params = []

            if search:
                query += " WHERE (c.first_name LIKE %s OR c.last_name LIKE %s OR c.email LIKE %s)"
                params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

            query += " ORDER BY c.last_name, c.first_name"

            # Get total count
            count_query = "SELECT COUNT(*) as total FROM customer c"
            if search:
                count_query += " WHERE (c.first_name LIKE %s OR c.last_name LIKE %s OR c.email LIKE %s)"

            cur.execute(count_query, params)
            total = cur.fetchone()["total"]

            # Apply pagination
            query += " LIMIT %s OFFSET %s"
            params.extend([per_page, (page - 1) * per_page])

            cur.execute(query, params)
            customers = cur.fetchall()

        conn.close()

        total_pages = (total + per_page - 1) // per_page
        return render_template(
            "customers.html",
            customers=customers,
            search=search,
            page=page,
            total_pages=total_pages,
            total=total,
        )
    except Exception as e:
        flash(f"Error fetching customers: {str(e)}", "error")
        return render_template(
            "customers.html",
            customers=[],
            search=search,
            page=1,
            total_pages=1,
            total=0,
        )


# Rentals Management
@app.route("/rentals")
def rentals():
    status = request.args.get("status", "active")  # active, returned, all
    page = request.args.get("page", 1, type=int)
    per_page = 20

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            query = """
                SELECT r.rental_id, r.rental_date, r.return_date,
                       f.title, f.film_id,
                       c.first_name, c.last_name, c.customer_id,
                       s.first_name as staff_first, s.last_name as staff_last,
                       p.amount
                FROM rental r
                JOIN inventory i ON r.inventory_id = i.inventory_id
                JOIN film f ON i.film_id = f.film_id
                JOIN customer c ON r.customer_id = c.customer_id
                JOIN staff s ON r.staff_id = s.staff_id
                LEFT JOIN payment p ON r.rental_id = p.rental_id
            """
            params = []

            if status == "active":
                query += " WHERE r.return_date IS NULL"
            elif status == "returned":
                query += " WHERE r.return_date IS NOT NULL"

            query += " ORDER BY r.rental_date DESC"

            # Get total count
            count_query = "SELECT COUNT(*) as total FROM rental r"
            if status == "active":
                count_query += " WHERE r.return_date IS NULL"
            elif status == "returned":
                count_query += " WHERE r.return_date IS NOT NULL"

            cur.execute(count_query)
            total = cur.fetchone()["total"]

            # Apply pagination
            query += " LIMIT %s OFFSET %s"
            params.extend([per_page, (page - 1) * per_page])

            cur.execute(query, params)
            rentals = cur.fetchall()

        conn.close()

        total_pages = (total + per_page - 1) // per_page
        return render_template(
            "rentals.html",
            rentals=rentals,
            status=status,
            page=page,
            total_pages=total_pages,
            total=total,
        )
    except Exception as e:
        flash(f"Error fetching rentals: {str(e)}", "error")
        return render_template(
            "rentals.html", rentals=[], status=status, page=1, total_pages=1, total=0
        )


# Staff Management
@app.route("/staff")
def staff():
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.staff_id, s.first_name, s.last_name, s.email, s.active,
                       a.address, a.district, ci.city, co.country,
                       s.username, s.last_update,
                       (SELECT COUNT(*) FROM rental r WHERE r.staff_id = s.staff_id) as rental_count
                FROM staff s
                JOIN address a ON s.address_id = a.address_id
                JOIN city ci ON a.city_id = ci.city_id
                JOIN country co ON ci.country_id = co.country_id
                ORDER BY s.last_name, s.first_name
            """
            )
            staff_list = cur.fetchall()
        conn.close()
        return render_template("staff.html", staff_list=staff_list)
    except Exception as e:
        flash(f"Error fetching staff: {str(e)}", "error")
        return render_template("staff.html", staff_list=[])


# Inventory Management
@app.route("/inventory")
def inventory():
    film_filter = request.args.get("film", "")
    store_filter = request.args.get("store", "")
    status_filter = request.args.get("status", "all")  # all, available, rented
    page = request.args.get("page", 1, type=int)
    per_page = 20

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            query = """
                SELECT i.inventory_id, f.title, f.film_id, s.store_id,
                       CASE WHEN r.rental_id IS NOT NULL AND r.return_date IS NULL THEN 0 ELSE 1 END as available
                FROM inventory i
                JOIN film f ON i.film_id = f.film_id
                JOIN store s ON i.store_id = s.store_id
                LEFT JOIN rental r ON i.inventory_id = r.inventory_id AND r.return_date IS NULL
            """
            params = []
            conditions = []

            if film_filter:
                conditions.append("f.title LIKE %s")
                params.append(f"%{film_filter}%")

            if store_filter:
                conditions.append("s.store_id = %s")
                params.append(store_filter)

            if status_filter == "available":
                conditions.append("r.rental_id IS NULL OR r.return_date IS NOT NULL")
            elif status_filter == "rented":
                conditions.append("r.rental_id IS NOT NULL AND r.return_date IS NULL")

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY f.title, i.inventory_id"

            # Get total count
            count_query = """SELECT COUNT(*) as total FROM inventory i
    JOIN film f ON i.film_id = f.film_id
    JOIN store s ON i.store_id = s.store_id
    LEFT JOIN rental r ON i.inventory_id = r.inventory_id AND r.return_date IS NULL"""
            if conditions:
                count_query += " WHERE " + " AND ".join(conditions)

            cur.execute(count_query, params)
            total = cur.fetchone()["total"]

            # Apply pagination
            query += " LIMIT %s OFFSET %s"
            params.extend([per_page, (page - 1) * per_page])

            cur.execute(query, params)
            inventory_items = cur.fetchall()

            # Get films for filter dropdown
            cur.execute("SELECT DISTINCT title FROM film ORDER BY title LIMIT 100")
            films = [film["title"] for film in cur.fetchall()]

            # Get stores for filter dropdown
            cur.execute("SELECT DISTINCT store_id FROM store ORDER BY store_id")
            stores = [store["store_id"] for store in cur.fetchall()]

        conn.close()

        total_pages = (total + per_page - 1) // per_page
        return render_template(
            "inventory.html",
            inventory_items=inventory_items,
            films=films,
            stores=stores,
            film_filter=film_filter,
            store_filter=store_filter,
            status_filter=status_filter,
            page=page,
            total_pages=total_pages,
            total=total,
        )
    except Exception as e:
        flash(f"Error fetching inventory: {str(e)}", "error")
        return render_template(
            "inventory.html",
            inventory_items=[],
            films=[],
            stores=[],
            film_filter=film_filter,
            store_filter=store_filter,
            status_filter=status_filter,
            page=1,
            total_pages=1,
            total=0,
        )


# Store Management
@app.route("/stores")
def stores():
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.store_id,
                       a.address, a.district, a.postal_code,
                       ci.city, co.country,
                       st.first_name as manager_first, st.last_name as manager_last,
                       (SELECT COUNT(*) FROM customer c WHERE c.store_id = s.store_id) as customer_count,
                       (SELECT COUNT(*) FROM inventory i WHERE i.store_id = s.store_id) as inventory_count,
                       (SELECT COUNT(*) FROM staff stf WHERE stf.store_id = s.store_id) as staff_count
                FROM store s
                JOIN address a ON s.address_id = a.address_id
                JOIN city ci ON a.city_id = ci.city_id
                JOIN country co ON ci.country_id = co.country_id
                JOIN staff st ON s.manager_staff_id = st.staff_id
                ORDER BY s.store_id
            """
            )
            stores = cur.fetchall()
        conn.close()
        return render_template("stores.html", stores=stores)
    except Exception as e:
        flash(f"Error fetching stores: {str(e)}", "error")
        return render_template("stores.html", stores=[])


# Reports and Analytics
@app.route("/reports")
def reports():
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Monthly revenue
            cur.execute(
                """
                SELECT YEAR(payment_date) as year, MONTH(payment_date) as month,
                       SUM(amount) as revenue, COUNT(*) as transactions
                FROM payment
                GROUP BY YEAR(payment_date), MONTH(payment_date)
                ORDER BY year DESC, month DESC
                LIMIT 12
            """
            )
            monthly_revenue = cur.fetchall()

            # Top films by revenue
            cur.execute(
                """
                SELECT f.title, c.name as category, SUM(p.amount) as revenue,
                       COUNT(r.rental_id) as rental_count
                FROM film f
                JOIN inventory i ON f.film_id = i.film_id
                JOIN rental r ON i.inventory_id = r.inventory_id
                JOIN payment p ON r.rental_id = p.rental_id
                LEFT JOIN film_category fc ON f.film_id = fc.film_id
                LEFT JOIN category c ON fc.category_id = c.category_id
                GROUP BY f.film_id, f.title, c.name
                ORDER BY revenue DESC
                LIMIT 10
            """
            )
            top_films = cur.fetchall()

            # Customer activity
            cur.execute(
                """
                SELECT c.first_name, c.last_name, c.email,
                       COUNT(r.rental_id) as rental_count,
                       SUM(p.amount) as total_spent
                FROM customer c
                LEFT JOIN rental r ON c.customer_id = r.customer_id
                LEFT JOIN payment p ON r.rental_id = p.rental_id
                GROUP BY c.customer_id, c.first_name, c.last_name, c.email
                ORDER BY total_spent DESC
                LIMIT 10
            """
            )
            top_customers = cur.fetchall()

        conn.close()
        return render_template(
            "reports.html",
            monthly_revenue=monthly_revenue,
            top_films=top_films,
            top_customers=top_customers,
        )
    except Exception as e:
        flash(f"Error generating reports: {str(e)}", "error")
        return render_template(
            "reports.html", monthly_revenue=[], top_films=[], top_customers=[]
        )


@app.route("/rentals/return/<int:rental_id>", methods=["POST"])
def return_rental(rental_id):
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE rental SET return_date = NOW() WHERE rental_id = %s AND return_date IS NULL",
                (rental_id,),
            )
            if cur.rowcount == 0:
                flash("Rental not found or already returned.", "error")
            else:
                conn.commit()
                flash("Rental marked as returned!", "success")
        conn.close()
    except Exception as e:
        flash(f"Error returning rental: {str(e)}", "error")
    return redirect(url_for("rentals"))


@app.route("/customers/<int:customer_id>/rentals")
def customer_rentals(customer_id):
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.customer_id, c.first_name, c.last_name, c.email
                FROM customer c WHERE c.customer_id = %s
            """,
                (customer_id,),
            )
            customer = cur.fetchone()
            if not customer:
                flash("Customer not found!", "error")
                return redirect(url_for("customers"))

            cur.execute(
                """
                SELECT r.rental_id, r.rental_date, r.return_date,
                       f.title, f.film_id, p.amount,
                       s.first_name as staff_first, s.last_name as staff_last
                FROM rental r
                JOIN inventory i ON r.inventory_id = i.inventory_id
                JOIN film f ON i.film_id = f.film_id
                JOIN staff s ON r.staff_id = s.staff_id
                LEFT JOIN payment p ON r.rental_id = p.rental_id
                WHERE r.customer_id = %s
                ORDER BY r.rental_date DESC
            """,
                (customer_id,),
            )
            rentals = cur.fetchall()

            cur.execute(
                """
                SELECT COUNT(*) as total_rentals,
                       SUM(p.amount) as total_spent
                FROM rental r
                LEFT JOIN payment p ON r.rental_id = p.rental_id
                WHERE r.customer_id = %s
            """,
                (customer_id,),
            )
            stats = cur.fetchone()
        conn.close()
        return render_template(
            "customer_rentals.html", customer=customer, rentals=rentals, stats=stats
        )
    except Exception as e:
        flash(f"Error loading customer rentals: {str(e)}", "error")
        return redirect(url_for("customers"))


@app.route("/api/dashboard/charts")
def dashboard_charts():
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Revenue by month
            cur.execute(
                """
                SELECT DATE_FORMAT(payment_date, '%%Y-%%m') as month, SUM(amount) as revenue
                FROM payment
                GROUP BY DATE_FORMAT(payment_date, '%%Y-%%m')
                ORDER BY month DESC LIMIT 12
            """
            )
            monthly_revenue = cur.fetchall()

            # Rentals by category
            cur.execute(
                """
                SELECT c.name as category, COUNT(r.rental_id) as rental_count
                FROM category c
                JOIN film_category fc ON c.category_id = fc.category_id
                JOIN film f ON fc.film_id = f.film_id
                JOIN inventory i ON f.film_id = i.film_id
                JOIN rental r ON i.inventory_id = r.inventory_id
                GROUP BY c.name
                ORDER BY rental_count DESC
            """
            )
            category_rentals = cur.fetchall()

            # Film ratings distribution
            cur.execute(
                """
                SELECT rating, COUNT(*) as count
                FROM film
                WHERE rating IS NOT NULL
                GROUP BY rating
                ORDER BY rating
            """
            )
            rating_distribution = cur.fetchall()

            # Rentals per day (last 30 days)
            cur.execute(
                """
                SELECT DATE(rental_date) as day, COUNT(*) as count
                FROM rental
                WHERE rental_date >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                GROUP BY DATE(rental_date)
                ORDER BY day
            """
            )
            daily_rentals = cur.fetchall()

        conn.close()
        return jsonify(
            {
                "monthly_revenue": monthly_revenue,
                "category_rentals": category_rentals,
                "rating_distribution": rating_distribution,
                "daily_rentals": daily_rentals,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/reports/charts")
def reports_charts():
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Revenue by store
            cur.execute(
                """
                SELECT s.store_id, SUM(p.amount) as revenue
                FROM payment p
                JOIN staff st ON p.staff_id = st.staff_id
                JOIN store s ON st.store_id = s.store_id
                GROUP BY s.store_id
            """
            )
            store_revenue = cur.fetchall()

            # Top 10 categories by revenue
            cur.execute(
                """
                SELECT c.name as category, SUM(p.amount) as revenue, COUNT(r.rental_id) as rentals
                FROM category c
                JOIN film_category fc ON c.category_id = fc.category_id
                JOIN film f ON fc.film_id = f.film_id
                JOIN inventory i ON f.film_id = i.film_id
                JOIN rental r ON i.inventory_id = r.inventory_id
                JOIN payment p ON r.rental_id = p.rental_id
                GROUP BY c.name
                ORDER BY revenue DESC
            """
            )
            category_revenue = cur.fetchall()

            # Customer spending distribution
            cur.execute(
                """
                SELECT
                    CASE
                        WHEN total < 50 THEN 'Under $50'
                        WHEN total < 100 THEN '$50-$100'
                        WHEN total < 150 THEN '$100-$150'
                        ELSE 'Over $150'
                    END as spending_range,
                    COUNT(*) as customer_count
                FROM (
                    SELECT c.customer_id, COALESCE(SUM(p.amount), 0) as total
                    FROM customer c
                    LEFT JOIN payment p ON c.customer_id = p.customer_id
                    GROUP BY c.customer_id
                ) sub
                GROUP BY spending_range
                ORDER BY MIN(total)
            """
            )
            spending_distribution = cur.fetchall()

        conn.close()
        return jsonify(
            {
                "store_revenue": store_revenue,
                "category_revenue": category_revenue,
                "spending_distribution": spending_distribution,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
