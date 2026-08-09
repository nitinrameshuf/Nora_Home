"""Makes tests/ a real package, which it has to be — not for tidiness.

django-vite 3.1.0 installs its own top-level `tests` package into site-packages
(a packaging bug on their side: `pip show -f django-vite` lists tests/__init__.py
alongside django_vite/). A *regular* package beats a *namespace* package no
matter what sys.path order says, so with tests/ carrying no __init__.py the
import of `tests.contract_app` resolved into site-packages and every app-contract
test failed with ModuleNotFoundError.

That is worth a file rather than a note in a commit message: the next dependency
that ships a top-level `tests` will do the same thing silently, and this makes
it impossible.
"""
