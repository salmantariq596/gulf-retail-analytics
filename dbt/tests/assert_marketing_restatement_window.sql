-- Ad platforms restate the previous two days in each daily export. A spend date in
-- the future, or more than two days before the file date, means a broken export
-- (or a wrong assumption in our latest-file-wins logic).
select
    source_file,
    file_date,
    spend_date
from {{ ref('stg_marketing__spend') }}
where
    spend_date > file_date
    or spend_date < file_date - interval '2 days'
