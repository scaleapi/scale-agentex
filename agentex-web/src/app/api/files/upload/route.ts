import 'dotenv/config';
import {NextRequest, NextResponse} from 'next/server';

const SGP_API_KEY = process.env.SGP_API_KEY;
const SGP_ACCOUNT_ID = process.env.SGP_ACCOUNT_ID;
const SGP_API_URL = process.env.SGP_API_URL;

export async function POST(req: NextRequest) {
  if (!SGP_API_KEY || !SGP_ACCOUNT_ID) {
    return NextResponse.json({error: 'Missing API key or account ID'}, {status: 500});
  }

  try {
    const formData = await req.formData();
    const combined: File[] = [formData.get('file'), ...formData.getAll('files')].filter(
      (file): file is File => typeof file !== 'string' && file !== null
    );

    // POST v5/files appears to only support single file form data
    const results = await Promise.all(
      combined.map(
        async (
          file
        ): Promise<
          {data: unknown; error?: undefined} | {data?: undefined; error: string}
        > => {
          const formDataPayload = new FormData();
          formDataPayload.append('file', file);

          const response = await fetch(`${SGP_API_URL}/v5/files`, {
            method: 'POST',
            headers: {
              'x-api-key': SGP_API_KEY,
              'x-selected-account-id': SGP_ACCOUNT_ID,
            },
            body: formDataPayload,
          });

          if (!response.ok) {
            const errorText = await response.text();
            return {error: errorText};
          }

          const data = await response.json();
          return {data};
        }
      )
    );

    return NextResponse.json(
      results.map(result => result.data).filter(data => data !== undefined)
    );
  } catch (error: any) {
    console.error('Error uploading file:', error);
    return NextResponse.json(
      {error: error.message || 'File upload failed'},
      {status: 500}
    );
  }
}
