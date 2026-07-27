DROP TABLE IF EXISTS uber_ride_bookings_raw;
DROP TABLE IF EXISTS uber_ride_bookings;

CREATE TABLE uber_ride_bookings_raw (
    date TEXT, time TEXT, booking_id TEXT, booking_status TEXT, customer_id TEXT,
    vehicle_type TEXT, pickup_location TEXT, drop_location TEXT, avg_vtat TEXT,
    avg_ctat TEXT, cancelled_rides_by_customer TEXT,
    reason_for_cancelling_by_customer TEXT, cancelled_rides_by_driver TEXT,
    driver_cancellation_reason TEXT, incomplete_rides TEXT,
    incomplete_rides_reason TEXT, booking_value TEXT, ride_distance TEXT,
    driver_ratings TEXT, customer_rating TEXT, payment_method TEXT
);

.mode csv
.import --skip 1 ncr_ride_bookings.csv uber_ride_bookings_raw

CREATE TABLE uber_ride_bookings (
    row_id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    booking_id TEXT NOT NULL,
    booking_status TEXT NOT NULL,
    customer_id TEXT,
    vehicle_type TEXT NOT NULL,
    pickup_location TEXT,
    drop_location TEXT,
    avg_vtat REAL,
    avg_ctat REAL,
    cancelled_rides_by_customer INTEGER,
    reason_for_cancelling_by_customer TEXT,
    cancelled_rides_by_driver INTEGER,
    driver_cancellation_reason TEXT,
    incomplete_rides INTEGER,
    incomplete_rides_reason TEXT,
    booking_value REAL,
    ride_distance REAL,
    driver_ratings REAL,
    customer_rating REAL,
    payment_method TEXT
);

INSERT INTO uber_ride_bookings
SELECT
    rowid, date, time, booking_id, booking_status, customer_id, vehicle_type,
    pickup_location, drop_location,
    CAST(NULLIF(avg_vtat, 'null') AS REAL),
    CAST(NULLIF(avg_ctat, 'null') AS REAL),
    CAST(NULLIF(cancelled_rides_by_customer, 'null') AS INTEGER),
    NULLIF(reason_for_cancelling_by_customer, 'null'),
    CAST(NULLIF(cancelled_rides_by_driver, 'null') AS INTEGER),
    NULLIF(driver_cancellation_reason, 'null'),
    CAST(NULLIF(incomplete_rides, 'null') AS INTEGER),
    NULLIF(incomplete_rides_reason, 'null'),
    CAST(NULLIF(booking_value, 'null') AS REAL),
    CAST(NULLIF(ride_distance, 'null') AS REAL),
    CAST(NULLIF(driver_ratings, 'null') AS REAL),
    CAST(NULLIF(customer_rating, 'null') AS REAL),
    NULLIF(payment_method, 'null')
FROM uber_ride_bookings_raw;

DROP TABLE uber_ride_bookings_raw;
CREATE INDEX idx_uber_ride_bookings_booking_id ON uber_ride_bookings(booking_id);
CREATE INDEX idx_uber_ride_bookings_date ON uber_ride_bookings(date);
CREATE INDEX idx_uber_ride_bookings_status ON uber_ride_bookings(booking_status);
CREATE INDEX idx_uber_ride_bookings_vehicle ON uber_ride_bookings(vehicle_type);
