import math
import time

import streamlit as st

from utils.user_scope import activate_user_scope, clear_user_scope


AUTH0_PROVIDER = "auth0"


class InvalidIdentityError(ValueError):
    pass


def validate_identity_claims(
    claims: dict,
    *,
    now: int | float | None = None,
) -> tuple[str, str, int | float]:
    """Validate the claims required before activating private storage."""
    expires_at = claims.get("exp")

    if (
        not isinstance(expires_at, (int, float))
        or isinstance(expires_at, bool)
        or not math.isfinite(expires_at)
    ):
        raise InvalidIdentityError(
            "Sesiunea nu conține o dată de expirare validă. Autentifică-te din nou."
        )

    expiration = expires_at
    current_time = time.time() if now is None else now

    if expiration <= current_time:
        raise InvalidIdentityError(
            "Sesiunea a expirat. Autentifică-te din nou."
        )

    issuer = str(claims.get("iss") or "").strip()
    subject = str(claims.get("sub") or "").strip()

    if not issuer or not subject:
        raise InvalidIdentityError(
            "Identitatea Auth0 nu conține identificatorii obligatorii `iss` și `sub`."
        )

    return issuer, subject, expiration


def _auth0_is_configured() -> bool:
    try:
        auth = st.secrets["auth"]
        provider = auth[AUTH0_PROVIDER]
        return all(
            str(value or "").strip()
            for value in (
                auth["redirect_uri"],
                auth["cookie_secret"],
                provider["client_id"],
                provider["client_secret"],
                provider["server_metadata_url"],
            )
        )
    except (KeyError, TypeError, AttributeError, FileNotFoundError):
        return False
    except Exception:
        # Streamlit raises a dedicated secrets error when no secrets file exists.
        return False


def _user_claims() -> dict:
    try:
        return dict(st.user)
    except (TypeError, AttributeError):
        return {}


def _is_logged_in(claims: dict) -> bool:
    try:
        return bool(st.user.is_logged_in)
    except (AttributeError, TypeError):
        return bool(claims.get("is_logged_in"))


def _render_login_page():
    st.markdown(
        """
        <style>
        header[data-testid="stHeader"], section[data-testid="stSidebar"] {
            display: none;
        }
        .block-container {
            max-width: 520px;
            padding-top: 12vh;
        }
        .auth-brand {
            text-align: center;
            color: #101828;
            font-size: 2rem;
            font-weight: 850;
            margin-bottom: 0.4rem;
        }
        .auth-subtitle {
            text-align: center;
            color: #667085;
            line-height: 1.55;
            margin-bottom: 2rem;
        }
        </style>
        <div class="auth-brand">Research Journal AI</div>
        <div class="auth-subtitle">
            Creează un cont sau autentifică-te pentru a accesa spațiul tău de cercetare.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not _auth0_is_configured():
        st.error("Autentificarea Auth0 nu este configurată încă.")
        st.info(
            "Copiază `.streamlit/secrets.toml.example` ca "
            "`.streamlit/secrets.toml` și completează valorile Auth0."
        )
        return

    st.button(
        "Autentificare / Creează cont",
        type="primary",
        width="stretch",
        on_click=st.login,
        args=(AUTH0_PROVIDER,),
    )
    st.caption(
        "Contul, parola, verificarea emailului și recuperarea parolei sunt gestionate securizat de Auth0."
    )


def require_auth() -> dict:
    """Require an Auth0 session and activate private storage for this run."""
    clear_user_scope()
    claims = _user_claims()

    if not _is_logged_in(claims):
        _render_login_page()
        st.stop()

    try:
        issuer, subject, _ = validate_identity_claims(claims)
    except InvalidIdentityError as exc:
        st.error(str(exc))
        clear_user_scope()
        st.logout()
        st.stop()
        return {}

    activate_user_scope(issuer, subject)
    return claims


def current_user_profile() -> dict:
    claims = _user_claims()
    email = str(
        claims.get("email")
        or claims.get("preferred_username")
        or ""
    ).strip()
    name = str(
        claims.get("name")
        or claims.get("nickname")
        or email.split("@", 1)[0]
        or "Researcher"
    ).strip()
    return {
        "name": name,
        "email": email,
        "picture": str(claims.get("picture") or "").strip(),
    }


def logout():
    clear_user_scope()
    st.logout()
