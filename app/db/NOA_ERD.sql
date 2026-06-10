CREATE TABLE `seoul_spots` (
	`area_cd`	VARCHAR(50)	NULL,
	`name`	VARCHAR(255)	NULL,
	`category`	VARCHAR(50)	NULL
);

CREATE TABLE `tour_spots` (
	`content_id`	VARCHAR(50)	NULL,
	`name`	VARCHAR(255)	NULL,
	`image_url`	TEXT	NULL,
	`description`	TEXT	NULL,
	`address`	TEXT	NULL,
	`mapx`	NUMERIC(10,7)	NULL,
	`mapy`	NUMERIC(10,7)	NULL
);

CREATE TABLE `users` (
	`id`	SERIAL	NULL,
	`social_id`	VARCHAR(255)	NOT NULL,
	`provider`	VARCHAR(20)	NOT NULL,
	`email`	VARCHAR(255)	NULL,
	`name`	VARCHAR(100)	NULL,
	`created_at`	TIMESTAMP	NULL
);

CREATE TABLE `spot_mapping` (
	`id`	SERIAL	NULL,
	`area_cd`	VARCHAR(50)	NULL,
	`content_id`	VARCHAR(50)	NULL,
	`area_cd2`	VARCHAR(50)	NULL
);

CREATE TABLE `likes` (
	`id`	SERIAL	NULL,
	`social_id`	VARCHAR(255)	NOT NULL,
	`provider`	VARCHAR(20)	NOT NULL,
	`area_cd`	VARCHAR(50)	NULL,
	`created_at`	TIMESTAMP	NULL
);

CREATE TABLE `congestion_data` (
	`id`	SERIAL	NULL,
	`area_cd`	VARCHAR(50)	NULL,
	`congestion_level`	VARCHAR(20)	NULL,
	`updated_at`	TIMESTAMP	NULL
);

ALTER TABLE `seoul_spots` ADD CONSTRAINT `PK_SEOUL_SPOTS` PRIMARY KEY (
	`area_cd`
);

ALTER TABLE `tour_spots` ADD CONSTRAINT `PK_TOUR_SPOTS` PRIMARY KEY (
	`content_id`
);

ALTER TABLE `users` ADD CONSTRAINT `PK_USERS` PRIMARY KEY (
	`id`
);

ALTER TABLE `spot_mapping` ADD CONSTRAINT `PK_SPOT_MAPPING` PRIMARY KEY (
	`id`
);

ALTER TABLE `likes` ADD CONSTRAINT `PK_LIKES` PRIMARY KEY (
	`id`
);

ALTER TABLE `congestion_data` ADD CONSTRAINT `PK_CONGESTION_DATA` PRIMARY KEY (
	`id`
);

