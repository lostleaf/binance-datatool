# Historical archives

The domain covers discovering Binance historical archives, downloading them to local storage,
and verifying their integrity against SHA256 checksums.

## Language

**TradeType**:
The Binance market classification to which an archive belongs.
_Avoid_: Exchange type.

**DataFrequency**:
The archive partition frequency: the calendar period grouped into an archive file.
_Avoid_: Kline interval.

**DataType**:
The category of historical dataset contained in an archive.
_Avoid_: File format.

**ContractType**:
The futures contract settlement style, distinguishing perpetual contracts from contracts with
scheduled delivery.
_Avoid_: TradeType.

**interval**:
The time span represented by one K line, independent of the archive's DataFrequency.
_Avoid_: Archive frequency.

**Symbol**:
The market identifier for the instrument whose historical data is archived.

**Archive home**:
The root of the user's local historical archive storage.

**Downloaded**:
Successfully transferred to local storage. This does not establish Verified status.
_Avoid_: Verified.

**Up to date**:
Satisfies the rules for skipping a download. This does not establish Verified status.
_Avoid_: Verified.

**Verified**:
Has passed SHA256 comparison against the associated checksum.
_Avoid_: Downloaded, Up to date.
