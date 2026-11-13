# S3 Listing Protocol

The archive client communicates with data.binance.vision's S3-compatible XML listing API.

## Request Format

```
GET https://s3-ap-northeast-1.amazonaws.com/data.binance.vision
    ?delimiter=/&prefix=data/spot/daily/klines/
```

## Response Structure

**Directory listing (simplified):**

```xml
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <IsTruncated>false</IsTruncated>
  <NextMarker>...</NextMarker>
  <CommonPrefixes>
    <Prefix>data/spot/daily/klines/BTCUSDT/</Prefix>
  </CommonPrefixes>
  <CommonPrefixes>
    <Prefix>data/spot/daily/klines/ETHUSDT/</Prefix>
  </CommonPrefixes>
</ListBucketResult>
```

**File listing (simplified):**

```xml
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <IsTruncated>false</IsTruncated>
  <Contents>
    <Key>data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-03.zip</Key>
    <LastModified>2026-04-01T08:06:34.000Z</LastModified>
    <Size>1048</Size>
  </Contents>
  <Contents>
    <Key>data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-03.zip.CHECKSUM</Key>
    <LastModified>2026-04-01T08:06:34.000Z</LastModified>
    <Size>105</Size>
  </Contents>
</ListBucketResult>
```

## Key Behaviors

| Behavior | Detail |
|-----------|--------|
| **Pagination** | Directory and file listings share one pagination loop. S3 returns at most 1000 entries per page. When `IsTruncated` is `"true"`, the client uses `NextMarker`, or falls back to the last child prefix (directory listing) or object key (file listing). Directory pages without child prefixes also fall back to the last object key. A truncated page without any marker source ends the listing. |
| **XML parsing** | Standard-library `xml.etree.ElementTree` parses namespaced and unqualified XML. Absent, single, and repeated `CommonPrefixes` or `Contents` elements produce lists consistently. Field text retains whitespace normalization; XML without a `ListBucketResult` root is rejected. |
| **Retry with backoff** | HTTP requests use `tenacity` with exponential backoff (up to 5 attempts), retrying only on `aiohttp.ClientError` and `asyncio.TimeoutError`. |
| **Timestamp parsing** | `Contents.LastModified` strings are parsed via `datetime.fromisoformat` (with a `Z` → `+00:00` substitution) so every `ArchiveFile.last_modified` is tz-aware in UTC. |

The [listing parser benchmark](../../../benchmarks/README.md#xml-listing-parser)
compares complete file-record conversion against the original parser on the same
1,000-entry page.

## Proxy Support

`ArchiveClient` creates `aiohttp.ClientSession` with `trust_env=True` by default. This means
the session reads proxy configuration from standard environment variables:

- `http_proxy` / `HTTP_PROXY`
- `https_proxy` / `HTTPS_PROXY`
- `all_proxy` / `ALL_PROXY`
- `no_proxy` / `NO_PROXY`

No additional proxy configuration is needed at the application level.

---

See also: [Archive package](./) | [Archive client module](client.md) | [Architecture](../../architecture.md)
