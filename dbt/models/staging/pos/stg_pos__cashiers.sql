with

source as (
    select * from {{ source('pos', 'cashiers') }}
),

renamed as (
    select
        cashier_id,
        cashier_code,
        store_id,
        full_name as cashier_name,
        hired_on,
        is_active,
        -- training-mode logins ring up test sales that must never reach reporting
        cashier_code like 'TRN-%' as is_training_cashier,
        {{ to_utc('updated_at') }} as updated_at
    from source
)

select * from renamed
