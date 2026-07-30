# AI Research Journal

Aplicație Streamlit pentru organizarea proiectelor și experimentelor, observații
scrise sau audio, transcrieri, rezumate, bibliotecă de cercetare, mindmap și
redactarea lucrărilor asistată de AI.

## Autentificare Auth0

Aplicația folosește autentificarea OIDC nativă din Streamlit. Auth0 gestionează
crearea contului, autentificarea, verificarea emailului și recuperarea parolei.

### 1. Configurează aplicația în Auth0

În Auth0 Dashboard:

1. Creează o aplicație de tip **Regular Web Application**.
2. Activează o Database Connection și lasă activată opțiunea de self-service
   signup dacă utilizatorii trebuie să-și poată crea singuri conturi.
3. Adaugă în **Allowed Callback URLs**:
   `http://localhost:8501/oauth2callback`.
4. Adaugă în **Allowed Logout URLs** și **Allowed Web Origins**:
   `http://localhost:8501`.
5. Pentru producție, adaugă aceleași URL-uri folosind domeniul HTTPS public.

### 2. Configurează secretele Streamlit

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Completează `client_id`, `client_secret` și domeniul Auth0. Generează un
`cookie_secret` separat, de exemplu cu `openssl rand -hex 32`. Fișierul real
`secrets.toml` este ignorat de Git și nu trebuie publicat.

Instalează dependențele și pornește aplicația:

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

### Izolarea datelor

Fiecare identitate Auth0 primește automat:

- o bază SQLite privată;
- un director privat pentru fișierele audio;
- un director privat pentru bibliotecă;
- un director privat pentru figurile manuscriselor.

Cheia directorului este un hash al claim-urilor OIDC `iss` și `sub`; emailul nu
este folosit ca identificator deoarece se poate modifica.

Datele create înainte de activarea autentificării rămân în locațiile vechi. Ca
să le atribui explicit contului proprietar, setează în `.env`:

```dotenv
AUTH0_LEGACY_OWNER_SUB=auth0|user-id-din-auth0
AUTH0_LEGACY_OWNER_ISSUER=https://domeniul-tau.auth0.com/
```

Valorile se găsesc în profilul utilizatorului din Auth0 Dashboard. Fără această
configurație, niciun cont autentificat nu primește automat datele vechi.

Utilizatorii pot șterge definitiv spațiul lor de lucru din meniul contului.
Operația elimină baza de date și toate fișierele audio, documentele și figurile
din directoarele asociate identității lor. Pentru proprietarul configurat în
modul legacy, ștergerea automată este dezactivată pentru a evita eliminarea unui
director vechi configurat prea larg.

## Limite de resurse

Aplicația aplică în backend cote per utilizator și globale pentru Gemini,
OpenAlex și transcriere, limite de concurență, maximum cinci query-uri OpenAlex
într-o căutare și cote cumulative pentru fișiere. Valorile implicite sunt
documentate în `.env.example` și trebuie ajustate în funcție de capacitatea și
bugetul deploymentului. Contoarele sunt păstrate în `data/security_limits.db`;
toate instanțele care folosesc aceeași cheie API trebuie să folosească aceeași
bază de limite sau un echivalent centralizat oferit de platforma cloud.
