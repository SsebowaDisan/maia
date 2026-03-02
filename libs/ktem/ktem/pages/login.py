import hashlib
from pathlib import Path

import gradio as gr
from ktem.app import BasePage
from ktem.db.models import User, engine
from ktem.pages.resources.user import create_user
from sqlmodel import Session, select
from theflow.settings import settings as flowsettings

ASSETS_IMG_DIR = Path(__file__).resolve().parents[1] / "assets" / "img"
MAIA_ICON_SVG_PATH = ASSETS_IMG_DIR / "favicon.svg"
MAIA_WHITE_ICON_SVG_PATH = ASSETS_IMG_DIR / "maia-white_icon.svg"


def _read_svg(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


MAIA_ICON_SVG = _read_svg(MAIA_ICON_SVG_PATH)
MAIA_WHITE_ICON_SVG = _read_svg(MAIA_WHITE_ICON_SVG_PATH)
HERO_ICON_SVG = MAIA_WHITE_ICON_SVG or MAIA_ICON_SVG

fetch_creds = """
function() {
    try {
        const username = localStorage.getItem("username") || "";
        const password = localStorage.getItem("password") || "";
        return [username, password];
    } catch (e) {
        return ["", ""];
    }
}
"""

signin_js = """
function(usn, pwd) {
    const usnEl = document.querySelector("#maia-login-username textarea, #maia-login-username input");
    const pwdEl = document.querySelector("#maia-login-password textarea, #maia-login-password input");
    const resolvedUsn = ((usnEl && usnEl.value) ? usnEl.value : (usn || "")).trim();
    const resolvedPwd = (pwdEl && typeof pwdEl.value === "string") ? pwdEl.value : (pwd || "");
    try {
        localStorage.setItem("username", resolvedUsn);
        localStorage.setItem("password", resolvedPwd);
    } catch (e) {}
    return [resolvedUsn, resolvedPwd];
}
"""

class LoginPage(BasePage):

    public_events = ["onSignIn"]

    def __init__(self, app):
        self._app = app
        self._ensure_bootstrap_admin()
        self.on_building_ui()

    def _ensure_bootstrap_admin(self):
        admin_username = str(
            getattr(flowsettings, "KH_FEATURE_USER_MANAGEMENT_ADMIN", "")
        ).strip()
        admin_password = str(
            getattr(flowsettings, "KH_FEATURE_USER_MANAGEMENT_PASSWORD", "")
        )
        if not admin_username or not admin_password:
            return

        normalized_username_lower = admin_username.lower()
        hashed_password = hashlib.sha256(admin_password.encode()).hexdigest()

        with Session(engine) as session:
            existing_user = session.exec(
                select(User).where(User.username_lower == normalized_username_lower)
            ).first()

            if existing_user is None:
                create_user(admin_username, admin_password, is_admin=True)
                return

            needs_update = False
            if existing_user.username != admin_username:
                existing_user.username = admin_username
                needs_update = True
            if existing_user.password != hashed_password:
                existing_user.password = hashed_password
                needs_update = True
            if not existing_user.admin:
                existing_user.admin = True
                needs_update = True

            if needs_update:
                session.add(existing_user)
                session.commit()

    def on_building_ui(self):
        with gr.Row(elem_id="maia-login-shell"):
            with gr.Column(elem_id="maia-login-hero", scale=1, min_width=320):
                gr.HTML(
                    f"""
                    <div class="maia-login-hero-inner">
                      <div class="maia-login-hero-logo" aria-hidden="true">{HERO_ICON_SVG}</div>
                      <h2>Welcome back</h2>
                      <p>
                        Sign in to access your {self._app.app_name} workspace
                        and continue where you left off
                      </p>
                    </div>
                    """
                )

            with gr.Column(elem_id="maia-login-form-panel", scale=1, min_width=360):
                gr.HTML(
                    f"""
                    <div class="maia-login-form-intro">
                      <p class="maia-login-kicker">{self._app.app_name}</p>
                      <h1>Sign in</h1>
                      <p>Enter your credentials to access your account</p>
                    </div>
                    """
                )
                self.usn = gr.Textbox(
                    label="Email or Phone Number",
                    placeholder="name@example.com",
                    visible=True,
                    elem_id="maia-login-username",
                )
                self.pwd = gr.Textbox(
                    label="Password",
                    type="password",
                    placeholder="Enter your password",
                    visible=True,
                    elem_id="maia-login-password",
                )
                gr.HTML(
                    """
                    <div class="maia-login-options" aria-hidden="true">
                      <label class="maia-login-remember">
                        <input type="checkbox" />
                        <span>Remember me</span>
                      </label>
                      <a href="#" onclick="return false;">Forgot password?</a>
                    </div>
                    """
                )
                self.btn_login = gr.Button(
                    "Sign In",
                    visible=True,
                    elem_id="maia-login-submit",
                    variant="primary",
                )
                gr.HTML(
                    """
                    <div class="maia-login-divider"><span>OR</span></div>
                    <p class="maia-login-footnote">
                      Don't have a Maia account? Contact your workspace admin to get access.
                    </p>
                    """
                )

    def on_register_events(self):
        onSignIn = gr.on(
            triggers=[self.btn_login.click, self.pwd.submit],
            fn=self.login,
            inputs=[self.usn, self.pwd],
            outputs=[self._app.user_id, self.usn, self.pwd],
            show_progress="hidden",
            js=signin_js,
        ).then(
            self.toggle_login_visibility,
            inputs=[self._app.user_id],
            outputs=[self.usn, self.pwd, self.btn_login],
        )
        for event in self._app.get_event("onSignIn"):
            onSignIn = onSignIn.success(**event)

    def toggle_login_visibility(self, user_id):
        return (
            gr.update(visible=user_id is None),
            gr.update(visible=user_id is None),
            gr.update(visible=user_id is None),
        )

    def _on_app_created(self):
        onSignIn = self._app.app.load(
            self.login,
            inputs=[self.usn, self.pwd],
            outputs=[self._app.user_id, self.usn, self.pwd],
            show_progress="hidden",
            js=fetch_creds,
        ).then(
            self.toggle_login_visibility,
            inputs=[self._app.user_id],
            outputs=[self.usn, self.pwd, self.btn_login],
        )
        for event in self._app.get_event("onSignIn"):
            onSignIn = onSignIn.success(**event)

    def on_subscribe_public_events(self):
        self._app.subscribe_event(
            name="onSignOut",
            definition={
                "fn": self.toggle_login_visibility,
                "inputs": [self._app.user_id],
                "outputs": [self.usn, self.pwd, self.btn_login],
                "show_progress": "hidden",
            },
        )

    def login(self, usn, pwd, request: gr.Request):
        try:
            import gradiologin as grlogin

            user = grlogin.get_user(request)
        except Exception:
            user = None

        if user:
            user_id = user["sub"]
            with Session(engine) as session:
                stmt = select(User).where(
                    User.id == user_id,
                )
                result = session.exec(stmt).all()

            if result:
                print("Existing user:", user)
                return user_id, "", ""
            else:
                print("Creating new user:", user)
                create_user(
                    usn=user["email"],
                    pwd="",
                    user_id=user_id,
                    is_admin=False,
                )
                return user_id, "", ""
        else:
            username = (usn or "").strip()
            if not username or not pwd:
                gr.Warning("Please enter both username and password")
                return None, usn, pwd

            bootstrap_admin_username = str(
                getattr(flowsettings, "KH_FEATURE_USER_MANAGEMENT_ADMIN", "")
            ).strip()
            bootstrap_admin_password = str(
                getattr(flowsettings, "KH_FEATURE_USER_MANAGEMENT_PASSWORD", "")
            )
            if (
                bootstrap_admin_username
                and bootstrap_admin_password
                and username.lower() == bootstrap_admin_username.lower()
                and pwd == bootstrap_admin_password
            ):
                with Session(engine) as session:
                    admin_user = session.exec(
                        select(User).where(
                            User.username_lower == bootstrap_admin_username.lower()
                        )
                    ).first()
                if admin_user:
                    return admin_user.id, "", ""

            hashed_password = hashlib.sha256(pwd.encode()).hexdigest()
            with Session(engine) as session:
                stmt = select(User).where(
                    User.username_lower == username.lower(),
                    User.password == hashed_password,
                )
                result = session.exec(stmt).all()
                if result:
                    return result[0].id, "", ""

                gr.Warning("Invalid username or password")
                return None, usn, pwd
