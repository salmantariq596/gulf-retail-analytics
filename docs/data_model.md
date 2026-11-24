# Target Data Model — Star Schema

Diagrams are written in Mermaid, which GitHub renders. The source-system schemas are described in [source_systems.md](source_systems.md).
Export an `erd.png` from dbdiagram.io or draw.io for the README once the marts are built.

## Lineage by layer

```mermaid
flowchart LR
  subgraph raw[Raw - loaded by dlt]
    rp[raw_pos.*] ; ro[raw_online.*] ; re[raw_erp.*] ; rc[raw_catalog.*] ; rm[raw_marketing.*]
  end
  subgraph stg[Staging - views, 1:1 with sources]
    s1[stg_pos__*] ; s2[stg_online__*] ; s3[stg_erp__*] ; s4[stg_catalog__products] ; s5[stg_marketing__spend]
  end
  subgraph snap[Snapshots - SCD2]
    sp[snap_products] ; ss[snap_stores] ; sc[snap_customers]
  end
  subgraph int[Intermediate]
    i1[int_pos_sale_lines_deduped] --> i3[int_sales_lines_unioned]
    i2[int_online_order_lines_valid] --> i3
    i3 --> i4[int_sales_lines_enriched<br/>AED, VAT split, cost on sale date]
    i5[int_customers_unified]
  end
  subgraph marts[Marts]
    f1[fct_sales_lines] ; f2[fct_returns] ; f3[fct_inventory_daily] ; f4[fct_online_orders] ; f5[fct_marketing_spend]
    d[dim_date / dim_store / dim_product / dim_customer / dim_channel / dim_promotion / dim_campaign]
  end
  raw --> stg --> int --> marts
  stg --> snap --> marts
  marts --> mf[MetricFlow metrics] --> ld[Lightdash]
```

## Star schema

```mermaid
erDiagram
  DIM_DATE ||--o{ FCT_SALES_LINES : "sale_date_key"
  DIM_STORE ||--o{ FCT_SALES_LINES : "store_key"
  DIM_PRODUCT ||--o{ FCT_SALES_LINES : "product_key (version at sale)"
  DIM_CUSTOMER |o--o{ FCT_SALES_LINES : "customer_key (nullable: walk-in)"
  DIM_CHANNEL ||--o{ FCT_SALES_LINES : "channel_key"
  DIM_PROMOTION |o--o{ FCT_SALES_LINES : "promotion_key"

  DIM_DATE ||--o{ FCT_RETURNS : "return_date_key"
  DIM_STORE ||--o{ FCT_RETURNS : "store_key"
  DIM_PRODUCT ||--o{ FCT_RETURNS : "product_key"
  DIM_CUSTOMER |o--o{ FCT_RETURNS : "customer_key"
  DIM_CHANNEL ||--o{ FCT_RETURNS : "original_channel_key"
  FCT_SALES_LINES |o--o{ FCT_RETURNS : "original_sale_line_key"

  DIM_DATE ||--o{ FCT_INVENTORY_DAILY : "snapshot_date_key"
  DIM_STORE ||--o{ FCT_INVENTORY_DAILY : "store_key"
  DIM_PRODUCT ||--o{ FCT_INVENTORY_DAILY : "product_key"

  DIM_DATE ||--o{ FCT_ONLINE_ORDERS : "placed/paid/shipped/delivered_date_key"
  DIM_STORE ||--o{ FCT_ONLINE_ORDERS : "store_key (virtual online)"
  DIM_CUSTOMER |o--o{ FCT_ONLINE_ORDERS : "customer_key"
  DIM_CHANNEL ||--o{ FCT_ONLINE_ORDERS : "channel_key"

  DIM_DATE ||--o{ FCT_MARKETING_SPEND : "spend_date_key"
  DIM_CAMPAIGN ||--o{ FCT_MARKETING_SPEND : "campaign_key"

  FCT_SALES_LINES {
    string sales_line_key PK "hash(source, sale/order id, line_number)"
    string source_system "pos | online"
    string transaction_id "degenerate: sale_id / order_id"
    int line_number
    int sale_date_key FK
    string store_key FK
    string product_key FK
    string customer_key FK
    string channel_key FK
    string promotion_key FK
    timestamp sold_at_local
    char currency_code
    int quantity
    decimal gross_amount_local_excl_vat
    decimal discount_amount_local_excl_vat
    decimal net_amount_local_excl_vat
    decimal vat_amount_local
    decimal gross_amount_aed_excl_vat
    decimal discount_amount_aed_excl_vat
    decimal net_amount_aed_excl_vat
    decimal net_amount_aed_incl_vat
    decimal vat_amount_aed
    decimal unit_cost_aed "valid on sale date"
    decimal cogs_aed
    decimal gross_margin_aed
    timestamp _loaded_at
  }
  FCT_RETURNS {
    string return_line_key PK
    string return_id "degenerate"
    string original_sale_line_key FK "nullable"
    int return_date_key FK
    string store_key FK
    string product_key FK
    string customer_key FK
    string reason_code
    int quantity
    decimal refund_aed_excl_vat
    decimal refund_vat_aed
    decimal returned_cogs_aed
    boolean has_receipt
  }
  FCT_INVENTORY_DAILY {
    string inventory_key PK "hash(date, store, sku)"
    int snapshot_date_key FK
    string store_key FK
    string product_key FK
    int qty_on_hand "SEMI-ADDITIVE"
    int qty_on_order "SEMI-ADDITIVE"
    decimal stock_value_at_cost_aed "SEMI-ADDITIVE"
    boolean is_out_of_stock
    boolean is_imputed "carried forward: file missing"
  }
  FCT_ONLINE_ORDERS {
    string order_key PK
    string order_id "degenerate"
    string customer_key FK
    string channel_key FK
    string store_key FK
    int placed_date_key FK
    int paid_date_key FK
    int shipped_date_key FK
    int delivered_date_key FK
    string current_status
    boolean is_cancelled
    int line_count
    decimal order_net_aed_excl_vat
    decimal hours_placed_to_paid
    decimal hours_paid_to_shipped
    decimal hours_shipped_to_delivered
    decimal hours_placed_to_delivered
  }
  FCT_MARKETING_SPEND {
    string marketing_spend_key PK
    int spend_date_key FK
    string campaign_key FK
    string marketing_channel
    char country_code
    decimal spend_aed
    int impressions
    int clicks
  }
  DIM_DATE {
    int date_key PK "YYYYMMDD"
    date date_day
    string hijri_date
    int hijri_year
    int hijri_month
    boolean is_ramadan
    string holiday_name
    boolean is_weekend_ae
    boolean is_weekend_sa
    boolean is_weekend_qa
  }
  DIM_STORE {
    string store_key PK "SCD2 version"
    string store_code "natural key"
    string store_name_en
    string store_name_ar
    char country_code
    string city
    string store_format
    char currency_code
    date opened_on
    date closed_on
    timestamp valid_from
    timestamp valid_to
    boolean is_current
  }
  DIM_PRODUCT {
    string product_key PK "SCD2 version"
    string sku "natural key"
    string product_name_en
    string product_name_ar
    string category
    string subcategory
    string brand
    decimal unit_cost_aed
    decimal list_price_aed
    boolean is_active
    timestamp valid_from
    timestamp valid_to
    boolean is_current
  }
  DIM_CUSTOMER {
    string customer_key PK "SCD2 version"
    string customer_id "unified natural key"
    string loyalty_number
    char country_code
    string loyalty_tier
    string acquisition_channel
    date first_purchase_date
    timestamp valid_from
    timestamp valid_to
    boolean is_current
  }
  DIM_CHANNEL {
    string channel_key PK
    string channel_code "store | web | app"
    string channel_group "offline | online"
  }
  DIM_PROMOTION {
    string promotion_key PK
    string promotion_code
    string discount_type
    decimal discount_value
    date starts_on
    date ends_on
  }
  DIM_CAMPAIGN {
    string campaign_key PK
    string campaign_id
    string campaign_name "latest"
    string marketing_channel
  }
```
