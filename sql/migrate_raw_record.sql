-- Move processing metadata out of legacy raw_record envelopes.
-- Storage-only migration: source identities and timestamps remain unchanged.
BEGIN;
LOCK TABLE iris_staging.signal_ingest IN ACCESS EXCLUSIVE MODE;
ALTER TABLE iris_staging.signal_ingest
    ADD COLUMN IF NOT EXISTS ingest_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

UPDATE iris_staging.signal_ingest
SET ingest_metadata = jsonb_build_object(
        'observation_flags', COALESCE(raw_record->'observation_flags', '[]'::jsonb),
        'a4_reference', raw_record->'a4_reference',
        'state_reference', raw_record->'state_reference'
    ) || ingest_metadata,
    raw_record = raw_record->'values'
WHERE jsonb_typeof(raw_record->'values') = 'object';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = 'iris_staging.signal_ingest'::regclass
                     AND conname = 'ck_ingest_metadata') THEN
        ALTER TABLE iris_staging.signal_ingest ADD CONSTRAINT ck_ingest_metadata
            CHECK (jsonb_typeof(ingest_metadata) = 'object');
    END IF;
END $$;
COMMIT;
