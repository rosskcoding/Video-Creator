#!/bin/bash
# ============================================
# Video-Creator Production Deployment Script
# ============================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_not_root() {
    if [ "$EUID" -eq 0 ]; then
        log_warning "Running as root is not recommended. Consider using a non-root user with docker group."
    fi
}

# Check required files
check_requirements() {
    log_info "Checking requirements..."
    
    cd "$PROJECT_DIR"
    
    if [ ! -f "$COMPOSE_FILE" ]; then
        log_error "docker-compose.prod.yml not found!"
        exit 1
    fi
    
    if [ ! -f "$ENV_FILE" ]; then
        log_error ".env.prod not found!"
        log_info "Copy env.prod.example to .env.prod and fill in your values:"
        log_info "  cp env.prod.example .env.prod"
        log_info "  nano .env.prod"
        exit 1
    fi
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed!"
        exit 1
    fi
    
    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed!"
        exit 1
    fi
    
    log_success "All requirements met"
}

# Validate environment variables
validate_env() {
    log_info "Validating environment variables..."
    
    # Parse .env as data, not code (avoid RCE via malicious .env)
    set -a
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
        # Remove surrounding quotes from value
        value="${value%\"}"
        value="${value#\"}"
        value="${value%\'}"
        value="${value#\'}"
        export "$key=$value"
    done < "$ENV_FILE"
    set +a
    
    local required_vars=(
        "DOMAIN"
        "ACME_EMAIL"
        "ADMIN_PASSWORD"
        "SECRET_KEY"
        "POSTGRES_PASSWORD"
        "OPENAI_API_KEY"
        "ELEVENLABS_API_KEY"
    )
    
    local missing=()
    
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            missing+=("$var")
        fi
    done
    
    if [ ${#missing[@]} -ne 0 ]; then
        log_error "Missing required environment variables:"
        for var in "${missing[@]}"; do
            echo "  - $var"
        done
        exit 1
    fi
    
    # Check for default values
    if [ "$ADMIN_PASSWORD" = "your-secure-admin-password-here" ]; then
        log_error "ADMIN_PASSWORD has default value! Please change it."
        exit 1
    fi
    
    if [ "$SECRET_KEY" = "your-64-character-hex-secret-key-here-generate-with-openssl" ]; then
        log_error "SECRET_KEY has default value! Generate with: openssl rand -hex 32"
        exit 1
    fi
    
    if [ "$POSTGRES_PASSWORD" = "your-secure-postgres-password-here" ]; then
        log_error "POSTGRES_PASSWORD has default value! Please change it."
        exit 1
    fi
    
    log_success "Environment variables validated"
}

# Pull latest images (if using registry)
pull_images() {
    if [ "$1" != "--no-pull" ]; then
        log_info "Pulling latest images..."
        if ! docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" pull; then
            log_warning "Some images failed to pull. This is OK if building locally."
            log_warning "If using a registry, check your credentials and image names."
        fi
        log_success "Images pull step completed"
    else
        log_info "Skipping image pull (--no-pull flag)"
    fi
}

# Build images locally (if not using registry)
build_images() {
    log_info "Building images..."
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build
    log_success "Images built"
}

# Run database migrations
run_migrations() {
    log_info "Running database migrations..."
    
    # Start only db service first
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d db
    
    # Wait for database to be ready
    log_info "Waiting for database to be ready..."
    sleep 10
    
    # Run migrations using the migrate profile
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" --profile migrate run --rm migrate
    
    log_success "Migrations completed"
}

# Start all services
start_services() {
    log_info "Starting services..."
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d
    log_success "Services started"
}

# Health check
health_check() {
    log_info "Running health checks..."
    
    local max_attempts=30
    local attempt=1
    local critical_services=("api" "frontend" "db" "redis")
    
    while [ $attempt -le $max_attempts ]; do
        local all_healthy=true
        local status_output
        
        for service in "${critical_services[@]}"; do
            # Get container ID for the service
            local container_id
            container_id=$(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps -q "$service" 2>/dev/null)
            
            if [ -z "$container_id" ]; then
                log_warning "Service $service not found"
                all_healthy=false
                continue
            fi
            
            # Check health status
            local health_status
            health_status=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$container_id" 2>/dev/null)
            
            case "$health_status" in
                "healthy"|"no-healthcheck")
                    # OK - either healthy or no healthcheck defined
                    ;;
                "starting")
                    all_healthy=false
                    ;;
                *)
                    log_warning "Service $service is $health_status"
                    all_healthy=false
                    ;;
            esac
        done
        
        if [ "$all_healthy" = true ]; then
            log_success "All critical services are healthy!"
            docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps
            return 0
        fi
        
        log_info "Waiting for services to be healthy... (attempt $attempt/$max_attempts)"
        sleep 10
        ((attempt++))
    done
    
    log_error "Health check timeout. Service status:"
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps
    return 1
}

# Show status
show_status() {
    log_info "Service status:"
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps
    
    # Parse DOMAIN from env file safely
    local DOMAIN
    DOMAIN=$(grep -E '^DOMAIN=' "$ENV_FILE" | head -1 | cut -d'=' -f2 | tr -d '"' | tr -d "'")
    echo ""
    log_success "Deployment complete!"
    echo ""
    echo "Your application is available at:"
    echo "  🌐 https://$DOMAIN"
    echo ""
    echo "Useful commands:"
    echo "  View logs:     docker compose -f $COMPOSE_FILE logs -f"
    echo "  Stop:          docker compose -f $COMPOSE_FILE down"
    echo "  Restart:       docker compose -f $COMPOSE_FILE restart"
    echo ""
}

# Main deployment flow
main() {
    echo ""
    echo "============================================"
    echo "  Video-Creator Production Deployment"
    echo "============================================"
    echo ""
    
    check_not_root
    check_requirements
    validate_env
    
    # Check for --build flag
    if [ "$1" = "--build" ]; then
        build_images
    else
        pull_images "$1"
    fi
    
    run_migrations
    start_services
    health_check
    show_status
}

# Run main with arguments
main "$@"

