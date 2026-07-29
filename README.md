$models = @(
    "qwen2.5-coder:14b-instruct-q8_0",
    "gemma2:27b",
    "qwen2.5-coder:32b",
    "llama3.1:70b-instruct-q2_K"
)

foreach ($model in $models) {
    Write-Host "Pulling $model..." -ForegroundColor Cyan
    ollama pull $model
    Write-Host "Successfully pulled $model`n" -ForegroundColor Green
}
