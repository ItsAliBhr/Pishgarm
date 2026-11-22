import json

from sqlalchemy import func, select

from app import paths
from app.db.models import (Account, Clause, Contact, Issuer, Item, LetterType, Party, Setting,
                           Unit)
from app.db.seed import load_seed


def _seed_len(name):
    return len(json.loads((paths.seed_dir() / f"{name}.json").read_text(encoding="utf-8")))


def test_seed_counts(db):
    with db() as s:
        count = lambda m: s.scalar(select(func.count()).select_from(m))  # noqa: E731
        assert count(Party) == 42
        assert count(Issuer) == 2
        assert count(Account) == 7
        assert count(LetterType) == 25
        assert count(Clause) == 45
        assert count(Item) == 55
        assert count(Unit) == _seed_len("units")
        assert count(Contact) > 0
        assert s.get(Setting, "output_root") is not None


def test_seed_is_idempotent_and_keeps_user_edits(db):
    with db() as s:
        p = s.scalar(select(Party).where(Party.code == "SARMAD"))
        p.phone = "031-0000000"
        s.commit()
        assert not any(load_seed(s).values())
        assert s.scalar(select(func.count()).select_from(Party)) == 42
        assert s.scalar(select(Party.phone).where(Party.code == "SARMAD")) == "031-0000000"


def test_issuers_linked_to_assets_and_accounts(db):
    with db() as s:
        company = s.scalar(select(Issuer).where(Issuer.code == "COMPANY"))
        personal = s.scalar(select(Issuer).where(Issuer.code == "PERSONAL"))
        assert company.stamp_image and company.vat_enabled_by_default
        assert personal.signature_image and personal.stamp_image is None
        assert (paths.user_assets_dir() / "stamp_company.jpg").exists()
        assert {a.code for a in company.accounts} == {"SADERAT_COMPANY"}


def test_seed_accounts_valid_and_open_question_defaults(db):
    from app.core.validators import iban_error
    with db() as s:
        accs = {a.code: a for a in s.scalars(select(Account))}
        assert all(iban_error(a.iban) is None for a in accs.values())
        assert accs["MELLI_BAHRAMI_61"].active is False
        assert accs["TEJARAT_HATAMI"].active is False


def test_contacts_mapped(db):
    with db() as s:
        p = s.scalar(select(Party).where(Party.code == "SARMAD"))
        assert p.contacts[0].honorific == "مهندس" and p.contacts[0].name == "شهسواری"
        assert p.contacts[0].is_default and p.contacts[0].title_prefix == "جناب آقای"
        assert p.contacts[1].position == "مدیرعامل"
