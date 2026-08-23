import csv
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.orm import Session

from api.database import make_engine
from api.models import Base, Tecnologia, Vaga
from scripts.export_seed import exportar_seed


def test_exportar_seed_gera_csv_corretamente():
    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        db_file = tmp_path / "test.db"
        output_csv = tmp_path / "seed.csv"

        engine = make_engine(f"sqlite:///{db_file}")
        try:
            Base.metadata.create_all(engine)

            with Session(engine) as db:
                t1 = Tecnologia(nome="Python", grupo="linguagens")
                t2 = Tecnologia(nome="Docker", grupo="cloud_devops")
                db.add_all([t1, t2])

                v1 = Vaga(
                    source="gupy",
                    external_id="101",
                    title="Dev Python Jr",
                    company="Empresa X",
                    location="São Paulo, SP",
                    workplace_type="Presencial",
                    area="Backend",
                    tecnologias=[t1, t2],
                )
                db.add(v1)
                db.commit()

            resultado = exportar_seed(db_path=db_file, output_csv=output_csv)
        finally:
            engine.dispose()


        assert resultado["total_vagas"] == 1
        assert output_csv.exists()

        with open(output_csv, encoding="utf-8-sig") as fh:
            reader = list(csv.DictReader(fh))
            assert len(reader) == 1
            assert reader[0]["source"] == "gupy"
            assert reader[0]["title"] == "Dev Python Jr"
            assert reader[0]["skills"] == "Docker, Python"
            assert reader[0]["workplace_type"] == "Presencial"
