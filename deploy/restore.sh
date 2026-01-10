#!/bin/bash
# ============================================
# Video-Creator Restore Script
# ============================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"

cd "$PROJECT_DIR"

# Check arguments
if [ -z "$1" ]; then
    log_error "Usage: $0 <backup-file.tar.gz>"
    echo ""
    echo "Available backups:"
    ls -la backups/*.tar.gz 2>/dev/null || echo "  No backups found"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    log_error "Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo ""
echo "============================================"
echo "  Video-Creator Restore"
echo "============================================"
echo ""

log_warning "This will OVERWRITE current data!"
read -p "Are you sure you want to continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    log_info "Restore cancelled"
    exit 0
fi

# Create temp directory
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Extract backup
log_info "Extracting backup..."
tar xzf "$BACKUP_FILE" -C "$TEMP_DIR"

# Find extracted files
DB_BACKUP=$(find "$TEMP_DIR" -name "*-db.sql" | head -1)
UPLOADS_BACKUP=$(find "$TEMP_DIR" -name "*-uploads.tar.gz" | head -1)
ENV_BACKUP=$(find "$TEMP_DIR" -name "*-env" | head -1)

# Stop services (except database)
log_info "Stopping application services..."
docker compose -f "$COMPOSE_FILE" stop api worker worker_convert frontend caddy || true

# Parse environment safely (avoid RCE via malicious .env)
POSTGRES_PASSWORD=$(grep -E '^POSTGRES_PASSWORD=' "$ENV_FILE" | head -1 | cut -d'=' -f2 | tr -d '"' | tr -d "'")

# Restore database
if [ -f "$DB_BACKUP" ]; then
    log_info "Restoring database..."
    
    # Ensure database is running
    docker compose -f "$COMPOSE_FILE" up -d db
    sleep 5
    
    # Drop and recreate database
    docker compose -f "$COMPOSE_FILE" exec -T db psql -U postgres -c "DROP DATABASE IF EXISTS presenter;"
    docker compose -f "$COMPOSE_FILE" exec -T db psql -U postgres -c "CREATE DATABASE presenter;"
    
    # Restore
    docker compose -f "$COMPOSE_FILE" exec -T db psql -U postgres presenter < "$DB_BACKUP"
    
    log_success "Database restored"
else
    log_warning "Database backup not found in archive"
fi

# Restore uploads
if [ -f "$UPLOADS_BACKUP" ]; then
    log_info "Restoring uploads..."
    
    # Clear existing data and restore
    docker run --rm \
        -v video-creator-uploads:/data \
        -v "$TEMP_DIR:/backup" \
        alpine sh -c "rm -rf /data/* && tar xzf /backup/*-uploads.tar.gz -C /data"
    
    log_success "Uploads restored"
else
    log_warning "Uploads backup not found in archive"
fi

# Optionally restore environment
if [ -f "$ENV_BACKUP" ]; then
    read -p "Restore environment file? (yes/no): " restore_env
    if [ "$restore_env" = "yes" ]; then
        cp "$ENV_BACKUP" "$ENV_FILE"
        log_success "Environment file restored"
    fi
fi

# Start all services
log_info "Starting services..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d

echo ""
log_success "Restore complete!"
echo ""
echo "Services are starting. Check status with:"
echo "  docker compose -f $COMPOSE_FILE ps"
echo ""

