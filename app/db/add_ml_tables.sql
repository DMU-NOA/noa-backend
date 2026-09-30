ALTER TABLE tour_spots
ADD COLUMN IF NOT EXISTS content_type_id VARCHAR(10);

ALTER TABLE tour_spots
ADD COLUMN IF NOT EXISTS category VARCHAR(50);

ALTER TABLE tour_spots
ADD COLUMN IF NOT EXISTS image_url2 TEXT;

ALTER TABLE tour_spots
ADD COLUMN IF NOT EXISTS event_start_date DATE;

ALTER TABLE tour_spots
ADD COLUMN IF NOT EXISTS event_end_date DATE;

ALTER TABLE tour_spots
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;


CREATE TABLE IF NOT EXISTS congestion_training_data (
    id BIGSERIAL PRIMARY KEY,

    area_cd VARCHAR(50) NOT NULL
        REFERENCES seoul_spots(area_cd),

    category VARCHAR(50),

    collected_at TIMESTAMPTZ NOT NULL,

    congestion_level VARCHAR(20) NOT NULL,

    congestion_label SMALLINT NOT NULL
        CHECK (congestion_label BETWEEN 0 AND 3),

    UNIQUE (area_cd, collected_at)
);


CREATE TABLE IF NOT EXISTS spot_reviews (
    id BIGSERIAL PRIMARY KEY,

    content_id VARCHAR(50) NOT NULL
        REFERENCES tour_spots(content_id),

    review_count INTEGER
        CHECK (review_count >= 0),

    rating NUMERIC(3, 2)
        CHECK (rating BETWEEN 0 AND 5),

    source VARCHAR(50),

    collected_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS predicted_congestion (
    id BIGSERIAL PRIMARY KEY,

    content_id VARCHAR(50) NOT NULL
        REFERENCES tour_spots(content_id),

    predicted_level VARCHAR(20) NOT NULL,

    predicted_label SMALLINT NOT NULL
        CHECK (predicted_label BETWEEN 0 AND 3),

    prediction_time TIMESTAMPTZ NOT NULL,

    model_version VARCHAR(50),

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);