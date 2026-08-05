# Performanță și deployment

## Ce este implementat

- cache privat per utilizator pentru citirile PostgreSQL, cu TTL scurt și
  invalidare imediată după orice mutație confirmată;
- pipeline PostgreSQL pentru contextul RLS și pentru grupurile de interogări
  independente din Experiments și Paper Writing;
- randare lazy pentru taburile principale și pentru graficele Data Analysis;
- eliminarea interogărilor N+1 din istoricul versiunilor și comentariilor;
- paginare/limite pentru versiuni, experimente, mesaje, audio și conversații AI;
- reutilizarea conexiunilor PostgreSQL, a conexiunilor HTTP către Storage și
  OpenAlex și a conexiunilor pentru rate-limit;
- URL-uri semnate cu durată scurtă pentru preview-urile private de imagine și
  audio, astfel încât fișierele să ajungă direct la browser;
- cache de maximum patru fișiere mari, timp de două minute, pentru dataseturile
  analizate repetat;
- migrarea Supabase `20260805150000_optimize_runtime_performance.sql`, care
  optimizează RLS și adaugă indexurile de runtime.

## Ce trebuie făcut la fiecare deployment

1. Publică modificările în branch-ul GitHub folosit de Streamlit Community
   Cloud.
2. Urmărește build-ul și verifică în log că sunt instalate exact
   `streamlit==1.58.0` și `starlette==1.3.1`.
3. Dacă build-ul nu pornește automat sau vrei golirea cache-urilor în memorie,
   deschide **Manage app → Reboot app**.
4. Autentifică-te și testează în ordine: Experiments → Library → Paper Writing
   → Data Analysis, apoi logout/login.
5. Verifică migrațiile cu:

```bash
supabase migration list --linked
supabase db lint --linked --level warning
```

Versiunea `20260805150000` trebuie să apară atât local, cât și remote.

## Setări recomandate

Pentru instanța actuală, păstrează în configurația de runtime:

```text
MIN_POSTGRES_POOL_SIZE=1
MAX_POSTGRES_POOL_SIZE=8
MAX_RESOURCE_LIMIT_POOL_SIZE=4
```

Conexiunea aplicației trebuie să rămână **Supavisor Session pooler**, port
`5432`, cu `sslmode=require`. Pool-ul aplicației păstrează conexiunile și evită
handshake-ul PostgreSQL la fiecare acțiune.

## Latența dintre regiuni

Streamlit Community Cloud găzduiește aplicațiile în Statele Unite, iar proiectul
Supabase actual este în `eu-central-1`. Cache-ul și pipeline-urile reduc mult
numărul de drumuri, dar nu pot elimina timpul fizic dintre regiuni.

Dacă dorești latența minimă, alege una dintre variante:

### Păstrezi Streamlit Community Cloud

1. Creezi un proiect Supabase nou într-o regiune din SUA.
2. Rulezi toate migrațiile din acest repository cu `supabase db push`.
3. Înlocuiești în Streamlit Secrets doar valorile din `[supabase]` și
   `[connections.supabase_postgres]`.
4. Nu modifici Auth0 Action. Callback-ul rămâne
   `https://ai-research-journal-vlad.streamlit.app/oauth2callback`.
5. Repornești aplicația și creezi un cont de test.

Aceasta este varianta cea mai simplă când nu există date de mutat.

### Păstrezi Supabase în Europa

Muti aplicația Streamlit pe un host Python/container din aceeași regiune sau
dintr-o regiune europeană apropiată. Trebuie apoi actualizate URL-ul Streamlit,
`redirect_uri`, Allowed Callback URLs, Allowed Logout URLs și Allowed Web
Origins din Auth0.

## Python

Nu este necesară schimbarea versiunii Python pentru corecția GZip; problema a
fost rezolvată prin versiunile compatibile din `requirements.txt`. Dacă dorești
totuși Python 3.13, Community Cloud cere ștergerea și redeployarea aplicației,
apoi selectarea versiunii în **Advanced settings**. Notează înainte subdomeniul,
secretele și coordonatele GitHub.
