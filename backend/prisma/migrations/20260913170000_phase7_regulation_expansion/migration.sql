-- AlterTable
ALTER TABLE "Regulation" ADD COLUMN IF NOT EXISTS "sourceDocumentId" TEXT;
ALTER TABLE "Regulation" ADD COLUMN IF NOT EXISTS "productCategory" TEXT;
ALTER TABLE "Regulation" ADD COLUMN IF NOT EXISTS "concentrationLimit" TEXT;

-- CreateIndex
CREATE INDEX IF NOT EXISTS "Regulation_jurisdiction_idx" ON "Regulation"("jurisdiction");
