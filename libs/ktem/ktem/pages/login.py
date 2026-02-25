import hashlib
from pathlib import Path

import gradio as gr
from ktem.app import BasePage
from ktem.db.models import User, engine
from ktem.pages.resources.user import create_user
from sqlmodel import Session, select

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
    const username = getStorage('username', '')
    const password = getStorage('password', '')
    return [username, password, null];
}
"""

signin_js = """
function(usn, pwd) {
    setStorage('username', usn);
    setStorage('password', pwd);
    return [usn, pwd];
}
"""

class LoginPage(BasePage):

    public_events = ["onSignIn"]

    def __init__(self, app):
        self._app = app
        self.on_building_ui()

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
                    visible=False,
                    elem_id="maia-login-username",
                )
                self.pwd = gr.Textbox(
                    label="Password",
                    type="password",
                    placeholder="Enter your password",
                    visible=False,
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
                    visible=False,
                    elem_id="maia-login-submit",
                    variant="primary",
                )
                gr.HTML(
                    """
                    <div class="maia-login-divider"><span>OR</span></div>
                    <p class="maia-login-footnote">Don't have a Maia account?</p>
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
        except (ImportError, AssertionError):
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
            if not usn or not pwd:
                return None, usn, pwd

            hashed_password = hashlib.sha256(pwd.encode()).hexdigest()
            with Session(engine) as session:
                stmt = select(User).where(
                    User.username_lower == usn.lower().strip(),
                    User.password == hashed_password,
                )
                result = session.exec(stmt).all()
                if result:
                    return result[0].id, "", ""

                gr.Warning("Invalid username or password")
                return None, usn, pwd
