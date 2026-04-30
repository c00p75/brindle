import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def test_groq():
    from groq import AsyncGroq
    
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("GROQ_API_KEY not found in env")
        return
        
    print(f"Key found: {api_key[:10]}...")
    
    client = AsyncGroq(api_key=api_key)
    try:
        response = await client.chat.completions.create(
            messages=[{"role": "user", "content": "Say 'AI is online'"}],
            model="llama-3.3-70b-versatile",
            max_tokens=20
        )
        print("AI Response:", response.choices[0].message.content)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test_groq())
