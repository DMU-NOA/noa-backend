CREATE TABLE IF NOT EXISTS congestion_training_data (
    id BIGSERIAL PRIMARY KEY,

    area_cd VARCHAR(50) NOT NULL
        REFERENCES seoul_spots(area_cd)
        ON DELETE CASCADE,

    category VARCHAR(50),

    collected_at TIMESTAMPTZ NOT NULL,

    congestion_level VARCHAR(20) NOT NULL,

    congestion_label SMALLINT NOT NULL
        CHECK (congestion_label BETWEEN 0 AND 3),

    UNIQUE (area_cd, collected_at)
);


CREATE TABLE IF NOT EXISTS latest_congestion (
    id BIGSERIAL PRIMARY KEY,

    area_cd VARCHAR(50)
        REFERENCES seoul_spots(area_cd)
        ON DELETE CASCADE,

    content_id VARCHAR(50)
        REFERENCES tour_spots(content_id)
        ON DELETE CASCADE,

    congestion_level VARCHAR(20) NOT NULL,

    congestion_label SMALLINT NOT NULL
        CHECK (congestion_label BETWEEN 0 AND 3),

    source VARCHAR(20) NOT NULL
        CHECK (source IN ('actual', 'predicted')),

    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);


CREATE UNIQUE INDEX IF NOT EXISTS uq_latest_actual
ON latest_congestion(area_cd)
WHERE source = 'actual';


CREATE UNIQUE INDEX IF NOT EXISTS uq_latest_predicted
ON latest_congestion(content_id)
WHERE source = 'predicted';