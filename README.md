# AI Research Journal

Aplicație Streamlit pentru organizarea proiectelor și experimentelor, observații
scrise sau audio, transcrieri, rezumate, bibliotecă de cercetare, mindmap și
redactarea lucrărilor asistată de AI. Pagina Data Analysis poate importa
dataseturi CSV, TSV, XLSX și JSON, rula fluxuri scikit-learn reproductibile și
exporta predicțiile și raportul fiecărei analize.

## Arhitectură cloud

În Streamlit, aplicația folosește:

- Auth0 pentru autentificare OIDC;
- PostgreSQL Supabase pentru toate datele aplicației;
- Supabase Storage pentru audio, Library, artefactele analizelor și imaginile
  manuscriselor;
- RLS bazat pe perechea verificată `iss` + `sub`, nu pe email.

SQLite și directoarele locale rămân disponibile ca backend de test/fallback.
Nu există migrare de date vechi în fluxul cloud; schema Supabase pornește goală.

## Autentificare Auth0

Aplicația folosește autentificarea OIDC nativă din Streamlit. Auth0 gestionează
crearea contului, autentificarea, verificarea emailului și recuperarea parolei.

### 1. Configurează aplicația în Auth0

În Auth0 Dashboard:

1. Creează o aplicație de tip **Regular Web Application**.
2. Activează o Database Connection și lasă activată opțiunea de self-service
   signup dacă utilizatorii trebuie să-și poată crea singuri conturi.
3. Adaugă în **Allowed Callback URLs**:
   `http://localhost:8501/oauth2callback` și
   `https://ai-research-journal-vlad.streamlit.app/oauth2callback`.
4. Adaugă în **Allowed Logout URLs** și **Allowed Web Origins**:
   `http://localhost:8501` și
   `https://ai-research-journal-vlad.streamlit.app`.
5. Creează un Action **Post Login**, adaugă-l în Login Flow și folosește:

```javascript
exports.onExecutePostLogin = async (event, api) => {
  api.idToken.setCustomClaim('role', 'authenticated');
};
```

Claimul trebuie să aibă cheia literală `role` și să fie pus în ID token.

### 2. Configurează secretele Streamlit

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Completează valorile Auth0 și Supabase. Generează un `cookie_secret` separat,
de exemplu cu `openssl rand -hex 32`. Păstrează obligatoriu
`expose_tokens = "id"`; ID tokenul este folosit numai server-side pentru
Supabase Storage. Fișierul real este ignorat de Git și nu trebuie publicat.

URL-ul PostgreSQL trebuie să fie cel de **Session pooler**, cu `sslmode=require`.
Driverul acceptă și forma Streamlit/SQLAlchemy
`postgresql+psycopg://...`.

Instalează dependențele și pornește aplicația:

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

### Schema Supabase

Migrațiile sunt în `supabase/migrations/`. Pentru un proiect nou:

```bash
supabase login
supabase link --project-ref YOUR_PROJECT_REF
supabase db push --dry-run
supabase db push
supabase db lint --linked --level warning
```

Migrațiile creează toate tabelele, funcțiile de identitate, RLS, contoarele
centralizate de rate-limit, ștergerea workspace-ului și bucket-urile private:
`audio`, `library`, `analysis-artifacts`, `manuscript-assets`.

### Izolarea datelor

La prima cerere, `ensure_current_app_user()` creează profilul aplicației din
claimurile Auth0 verificate. Fiecare tabel are `user_id`, relații tenant-safe și
RLS forțat. Obiectele Storage sunt salvate numai sub
`users/<app_user_uuid>/...`, iar politicile verifică același UUID.

Utilizatorii pot șterge definitiv spațiul lor de lucru din meniul contului.
Operația șterge întâi obiectele private din toate bucket-urile, apoi profilul și
toate datele PostgreSQL dependente.

## Limite de resurse

Aplicația aplică cote per utilizator și globale pentru Gemini, OpenAlex și
transcriere, plus limite de concurență. În cloud, contoarele și lease-urile sunt
centralizate în schema privată PostgreSQL `app_private`; în fallback-ul SQLite
rămân în `data/security_limits.db`. Valorile implicite sunt documentate în
`.env.example` și trebuie ajustate după bugetul deploymentului.
