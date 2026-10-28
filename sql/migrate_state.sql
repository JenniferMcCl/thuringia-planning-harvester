-- Upgrade the earlier prototype without losing identities or observation history.
-- Run explicitly once on an existing database; safe to repeat.
BEGIN;
LOCK TABLE iris_staging.signal_ingest IN ACCESS EXCLUSIVE MODE;
ALTER TABLE iris_staging.signal_ingest
    ADD COLUMN IF NOT EXISTS state_status TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE iris_staging.signal_ingest DROP CONSTRAINT IF EXISTS ck_accepted;
ALTER TABLE iris_staging.signal_ingest DROP CONSTRAINT IF EXISTS ck_screening_status;
ALTER TABLE iris_staging.signal_ingest DROP CONSTRAINT IF EXISTS ck_chronology;

-- A legacy accepted row has no verified state membership. This is a schema/data
-- correction, not a new source observation: last_seen_at must remain untouched.
UPDATE iris_staging.signal_ingest
SET screening_status = 'needs_review',
    quality_flags = quality_flags || '"state_revalidation_required"'::jsonb,
    content_updated_at = GREATEST(content_updated_at, CURRENT_TIMESTAMP)
WHERE (screening_status = 'accepted' AND state_status != 'inside')
   OR screening_status = 'excluded';

ALTER TABLE iris_staging.signal_ingest ADD CONSTRAINT ck_screening_status
    CHECK (screening_status IN ('accepted', 'needs_review'));
ALTER TABLE iris_staging.signal_ingest ADD CONSTRAINT ck_accepted
    CHECK (screening_status != 'accepted' OR
           (approval_status = 'approved' AND industrial_status = 'industrial'
            AND corridor_status = 'inside' AND state_status = 'inside' AND geom IS NOT NULL));
ALTER TABLE iris_staging.signal_ingest ADD CONSTRAINT ck_chronology
    CHECK (first_seen_at <= last_seen_at AND first_seen_at <= content_updated_at);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = 'iris_staging.signal_ingest'::regclass
                     AND conname = 'ck_state_status') THEN
        ALTER TABLE iris_staging.signal_ingest ADD CONSTRAINT ck_state_status
            CHECK (state_status IN ('inside', 'outside', 'unknown'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = 'iris_staging.signal_ingest'::regclass
                     AND conname = 'ck_state_geometry') THEN
        ALTER TABLE iris_staging.signal_ingest ADD CONSTRAINT ck_state_geometry
            CHECK (state_status = 'unknown' OR geom IS NOT NULL);
    END IF;
END $$;
COMMIT;
