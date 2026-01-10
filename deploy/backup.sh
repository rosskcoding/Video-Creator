#!/bin/bash
# ============================================
# Video-Creator Backup Script
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

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"
BACKUP_DIR="${PROJECT_DIR}/backups"
TIMESTAMP=$(date +"%Y-%m-%d-%H%M%S")
BACKUP_NAME="backup-${TIMESTAMP}"

cd "$PROJECT_DIR"

# Create backup directory
mkdir -p "$BACKUP_DIR"

echo ""
echo "============================================"
echo "  Video-Creator Backup"
echo "============================================"
echo ""

# Parse environment safely (avoid RCE via malicious .env)
# We only need POSTGRES_PASSWORD for this script
POSTGRES_PASSWORD=$(grep -E '^POSTGRES_PASSWORD=' "$ENV_FILE" | head -1 | cut -d'=' -f2 | tr -d '"' | tr -d "'")

# Backup PostgreSQL database
log_info "Backing up PostgreSQL database..."
docker compose -f "$COMPOSE_FILE" exec -T db pg_dump -U postgres presenter > "${BACKUP_DIR}/${BACKUP_NAME}-db.sql"
log_success "Database backed up"

# Backup uploads/data volume
log_info "Backing up uploads data..."
docker run --rm \
    -v video-creator-uploads:/data \
    -v "${BACKUP_DIR}:/backup" \
    alpine tar czf "/backup/${BACKUP_NAME}-uploads.tar.gz" -C /data .
log_success "Uploads backed up"

# Backup environment file (plaintext - handle with care!)
# WARNING: This contains sensitive secrets. Ensure backup storage is secure.
log_info "Backing up environment file (plaintext)..."
cp "$ENV_FILE" "${BACKUP_DIR}/${BACKUP_NAME}-env"
chmod 600 "${BACKUP_DIR}/${BACKUP_NAME}-env"
log_warning "Environment file backed up as PLAINTEXT. Consider encrypting with 'age' or 'gpg' for off-site storage."

# Create combined archive
log_info "Creating combined archive..."
cd "$BACKUP_DIR"
tar czf "${BACKUP_NAME}.tar.gz" \
    "${BACKUP_NAME}-db.sql" \
    "${BACKUP_NAME}-uploads.tar.gz" \
    "${BACKUP_NAME}-env"

# Cleanup individual files
rm -f "${BACKUP_NAME}-db.sql" "${BACKUP_NAME}-uploads.tar.gz" "${BACKUP_NAME}-env"

# Calculate size
BACKUP_SIZE=$(du -h "${BACKUP_NAME}.tar.gz" | cut -f1)

echo ""
log_success "Backup complete!"
echo ""
echo "Backup file: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
echo "Size: ${BACKUP_SIZE}"
echo ""
echo "To restore, run:"
echo "  ./deploy/restore.sh ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
echo ""

# Cleanup old backups (keep last 7)
log_info "Cleaning up old backups (keeping last 7)..."
cd "$BACKUP_DIR"
ls -t backup-*.tar.gz 2>/dev/null | tail -n +8 | xargs -r rm -f
log_success "Cleanup complete"

