-- Runs once, when the Docker volume is first created.
-- vaani_app is the role the API connects as. It is not a superuser and does not
-- own the tables, so the row-level security policies apply to every query it runs.
-- Migrations (run as vaani_admin) grant it table privileges.
CREATE ROLE vaani_app LOGIN PASSWORD 'vaani_app';
