
docs.vllm.ai
OpenAI-Compatible Server - vLLM
26~33분

vLLM provides an HTTP server that implements OpenAI's Completions API, Chat API, and more! This functionality lets you serve models and interact with them using an HTTP client.

API key authentication does not protect every endpoint

The --api-key option (or VLLM_API_KEY environment variable) only authenticates requests to endpoints under the /v1, /v2, and /inference path prefixes. Other endpoints on the same HTTP server are not authenticated — most notably /invocations, which exposes the same inference capabilities as the /v1 endpoints. Do not rely on --api-key alone to secure vLLM. See API Key Authentication Limitations for the full list of protected and unprotected endpoints and recommended hardening, such as deploying behind a reverse proxy.
Supported APIs¶

We currently support the following OpenAI APIs:

    Completions API (/v1/completions)
        Only applicable to text generation models.
        Note: suffix parameter is not supported.
    Chat Completions API (/v1/chat/completions)
        Only applicable to text generation models with a chat template.
        Note: user parameter is ignored.
        Note: Setting the parallel_tool_calls parameter to false ensures vLLM only returns zero or one tool call per request. Setting it to true (the default) allows returning more than one tool call per request. There is no guarantee more than one tool call will be returned if this is set to true, as that behavior is model dependent and not all models are designed to support parallel tool calls.
    Chat Completions batch API (/v1/chat/completions/batch)
    Responses API (/v1/responses, /v1/responses/{response_id}, /v1/responses/{response_id}/cancel)
        Only applicable to text generation models.
    Embeddings API (/v1/embeddings)
        Only applicable to embedding models.
    Transcriptions API (/v1/audio/transcriptions)
        Only applicable to Automatic Speech Recognition (ASR) models.
    Translation API (/v1/audio/translations)
        Only applicable to Automatic Speech Recognition (ASR) models.

Completions API¶

In your terminal, you can install vLLM, then start the server with the vllm serve command. (You can also use our Docker image.)

vllm serve NousResearch/Meta-Llama-3-8B-Instruct \
  --dtype auto \
  --api-key token-abc123

To call the server, in your preferred text editor, create a script that uses an HTTP client. Include any messages that you want to send to the model. Then run that script. Below is an example script using the official OpenAI Python client.
Code

Tip

vLLM supports some parameters that are not supported by OpenAI, top_k for example. You can pass these parameters to vLLM using the OpenAI client in the extra_body parameter of your requests, i.e. extra_body={"top_k": 50} for top_k.

Important

By default, the server applies generation_config.json from the Hugging Face model repository if it exists. This means the default values of certain sampling parameters can be overridden by those recommended by the model creator.

To disable this behavior, please pass --generation-config vllm when launching the server.

vLLM supports a set of parameters that are not part of the OpenAI API. In order to use them, you can pass them as extra parameters in the OpenAI client. Or directly merge them into the JSON payload if you are using HTTP call directly.

completion = client.chat.completions.create(
    model="NousResearch/Meta-Llama-3-8B-Instruct",
    messages=[
        {"role": "user", "content": "Classify this sentiment: vLLM is wonderful!"},
    ],
    extra_body={
        "structured_outputs": {"choice": ["positive", "negative"]},
    },
)

The X-Request-Id HTTP request header can be enabled with --enable-request-id-headers.
Code

The Completions, Chat Completions, and Responses APIs also support the X-Vllm-Priority request header. Its value must be an integer and overrides the priority value in the JSON request body. Non-zero priorities require the server to use priority scheduling.

completion = client.chat.completions.create(
    model="NousResearch/Meta-Llama-3-8B-Instruct",
    messages=[{"role": "user", "content": "Hello!"}],
    extra_headers={"X-Vllm-Priority": "-10"},
)

API Reference¶
Completions API¶

Our Completions API is compatible with OpenAI's Completions API; you can use the official OpenAI Python client to interact with it.

Code example: examples/basic/online_serving/openai_completion_client.py

The following sampling parameters are supported.
Code

The following extra parameters are supported:
Code

Chat API¶

Our Chat API is compatible with OpenAI's Chat Completions API; you can use the official OpenAI Python client to interact with it.

We support both Vision- and Audio-related parameters; see our Multimodal Inputs guide for more information.

    Note: image_url.detail parameter is not supported.

Code example: examples/basic/online_serving/openai_chat_completion_client.py

The following sampling parameters are supported.
Code

The following extra parameters are supported:
Code

Responses API¶

Our Responses API is compatible with OpenAI's Responses API; you can use the official OpenAI Python client to interact with it.

Code example: examples/tool_calling/openai_responses_client_with_tools.py

The following extra parameters in the request object are supported:
Code

The following extra parameters in the response object are supported:
Code


