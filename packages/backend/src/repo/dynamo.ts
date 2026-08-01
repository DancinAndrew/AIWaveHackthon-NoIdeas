import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import {
  DynamoDBDocumentClient,
  GetCommand,
  PutCommand,
  QueryCommand,
} from '@aws-sdk/lib-dynamodb';
import type {
  Booking,
  ChatSession,
  MatchResult,
  ServiceCategory,
  ServiceRequest,
  UserPreferences,
  UserProfile,
  Vendor,
} from '../domain/types';
import { config } from '../lib/config';
import { mergePrefs } from './memory';
import type { Repo } from './types';
import { vendorCovers } from './coverage';

/**
 * DynamoDB single-table design
 *
 * | 實體      | PK                  | SK        | GSI1PK        | GSI1SK              |
 * |-----------|---------------------|-----------|---------------|---------------------|
 * | 會員      | USER#<accountId>    | PROFILE   | -             | -                   |
 * | 廠商      | VENDOR#<vendorId>   | META      | VENDOR        | <vendorId>          |
 * | 服務單    | REQ#<requestId>     | META      | USER#<acc>    | REQ#<createdAt>     |
 * | 媒合結果  | REQ#<requestId>     | MATCH     | -             | -                   |
 * | 預約單    | BOOKING#<orderNo>   | META      | USER#<acc>    | BOOKING#<createdAt> |
 * | 對話      | SESSION#<sessionId> | META      | -             | -                   |
 */
const GSI1 = 'GSI1';

const doc = DynamoDBDocumentClient.from(new DynamoDBClient({ region: config.region }), {
  marshallOptions: { removeUndefinedValues: true },
});

interface Item {
  PK: string;
  SK: string;
  GSI1PK?: string;
  GSI1SK?: string;
  data: unknown;
}

export class DynamoRepo implements Repo {
  private table = config.tableName;

  private async get<T>(PK: string, SK: string): Promise<T | undefined> {
    const res = await doc.send(new GetCommand({ TableName: this.table, Key: { PK, SK } }));
    return (res.Item as Item | undefined)?.data as T | undefined;
  }

  private async put(item: Item): Promise<void> {
    await doc.send(new PutCommand({ TableName: this.table, Item: item }));
  }

  private async queryGsi1<T>(pk: string, skPrefix?: string): Promise<T[]> {
    const res = await doc.send(
      new QueryCommand({
        TableName: this.table,
        IndexName: GSI1,
        KeyConditionExpression: skPrefix
          ? 'GSI1PK = :pk AND begins_with(GSI1SK, :sk)'
          : 'GSI1PK = :pk',
        ExpressionAttributeValues: skPrefix ? { ':pk': pk, ':sk': skPrefix } : { ':pk': pk },
      }),
    );
    return (res.Items ?? []).map((i) => (i as Item).data as T);
  }

  // ---- 會員 ----
  getUser(id: string) {
    return this.get<UserProfile>(`USER#${id}`, 'PROFILE');
  }

  putUser(user: UserProfile) {
    return this.put({ PK: `USER#${user.inbrAccountId}`, SK: 'PROFILE', data: user });
  }

  async mergePreferences(id: string, patch: UserPreferences): Promise<UserPreferences> {
    const user = await this.getUser(id);
    if (!user) throw new Error(`user not found: ${id}`);
    user.preferences = mergePrefs(user.preferences, patch);
    await this.putUser(user);
    return user.preferences;
  }

  // ---- 廠商 ----
  async listVendors(filter?: {
    category?: ServiceCategory;
    countyCode?: string;
    districtCode?: string;
  }) {
    let list = await this.queryGsi1<Vendor>('VENDOR');
    if (filter?.category) list = list.filter((v) => v.categories.includes(filter.category!));
    if (filter?.countyCode) {
      list = list.filter((v) => vendorCovers(v, filter.countyCode!, filter.districtCode));
    }
    return list;
  }

  getVendor(vendorId: string) {
    return this.get<Vendor>(`VENDOR#${vendorId}`, 'META');
  }

  putVendor(vendor: Vendor) {
    return this.put({
      PK: `VENDOR#${vendor.vendorId}`,
      SK: 'META',
      GSI1PK: 'VENDOR',
      GSI1SK: vendor.vendorId,
      data: vendor,
    });
  }

  // ---- 服務單 ----
  getRequest(requestId: string) {
    return this.get<ServiceRequest>(`REQ#${requestId}`, 'META');
  }

  putRequest(req: ServiceRequest) {
    return this.put({
      PK: `REQ#${req.requestId}`,
      SK: 'META',
      GSI1PK: `USER#${req.inbrAccountId}`,
      GSI1SK: `REQ#${req.createdAt}`,
      data: req,
    });
  }

  listRequestsByUser(id: string) {
    return this.queryGsi1<ServiceRequest>(`USER#${id}`, 'REQ#');
  }

  // ---- 媒合結果 ----
  putMatch(match: MatchResult) {
    return this.put({ PK: `REQ#${match.requestId}`, SK: 'MATCH', data: match });
  }

  getMatch(requestId: string) {
    return this.get<MatchResult>(`REQ#${requestId}`, 'MATCH');
  }

  // ---- 預約單 ----
  putBooking(booking: Booking) {
    return this.put({
      PK: `BOOKING#${booking.orderNo}`,
      SK: 'META',
      GSI1PK: `USER#${booking.inbrAccountId}`,
      GSI1SK: `BOOKING#${booking.createdAt}`,
      data: booking,
    });
  }

  getBooking(orderNo: string) {
    return this.get<Booking>(`BOOKING#${orderNo}`, 'META');
  }

  listBookingsByUser(id: string) {
    return this.queryGsi1<Booking>(`USER#${id}`, 'BOOKING#');
  }

  // ---- 對話 ----
  getSession(sessionId: string) {
    return this.get<ChatSession>(`SESSION#${sessionId}`, 'META');
  }

  putSession(session: ChatSession) {
    return this.put({ PK: `SESSION#${session.sessionId}`, SK: 'META', data: session });
  }
}
