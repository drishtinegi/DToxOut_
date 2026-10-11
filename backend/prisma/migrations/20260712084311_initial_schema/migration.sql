-- CreateEnum
CREATE TYPE "Role" AS ENUM ('USER', 'ADMIN');

-- CreateEnum
CREATE TYPE "RiskLevel" AS ENUM ('LOW', 'MODERATE', 'HIGH', 'VERY_HIGH');

-- CreateEnum
CREATE TYPE "RegulatoryStatus" AS ENUM ('APPROVED', 'RESTRICTED', 'BANNED', 'PENDING_REVIEW');

-- CreateEnum
CREATE TYPE "EvidenceLevel" AS ENUM ('LOW', 'MODERATE', 'HIGH', 'VERY_HIGH');

-- CreateTable
CREATE TABLE "User" (
    "id" UUID NOT NULL,
    "email" TEXT NOT NULL,
    "username" TEXT NOT NULL,
    "hashedPassword" TEXT NOT NULL,
    "role" "Role" NOT NULL DEFAULT 'USER',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "User_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Scan" (
    "id" UUID NOT NULL,
    "userId" UUID NOT NULL,
    "productName" TEXT NOT NULL,
    "imageUrl" TEXT,
    "overallRiskScore" DOUBLE PRECISION NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Scan_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Ingredient" (
    "id" UUID NOT NULL,
    "inciName" TEXT NOT NULL,
    "commonName" TEXT,
    "description" TEXT NOT NULL,
    "categoryId" UUID,
    "safetyRating" DOUBLE PRECISION NOT NULL,
    "evidenceLevel" "EvidenceLevel" NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Ingredient_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "IngredientAlias" (
    "id" UUID NOT NULL,
    "ingredientId" UUID NOT NULL,
    "alias" TEXT NOT NULL,

    CONSTRAINT "IngredientAlias_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SafetyProfile" (
    "id" UUID NOT NULL,
    "ingredientId" UUID NOT NULL,
    "riskLevel" "RiskLevel" NOT NULL,
    "allergyRisk" TEXT NOT NULL,
    "pregnancyRisk" TEXT NOT NULL,
    "acneRisk" TEXT NOT NULL,
    "sensitiveSkinRisk" TEXT NOT NULL,
    "explanation" TEXT NOT NULL,

    CONSTRAINT "SafetyProfile_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Regulation" (
    "id" UUID NOT NULL,
    "ingredientId" UUID NOT NULL,
    "country" TEXT NOT NULL,
    "regulatoryStatus" "RegulatoryStatus" NOT NULL,
    "restrictionDetails" TEXT NOT NULL,
    "source" TEXT NOT NULL,

    CONSTRAINT "Regulation_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ScientificReference" (
    "id" UUID NOT NULL,
    "ingredientId" UUID NOT NULL,
    "title" TEXT NOT NULL,
    "organization" TEXT NOT NULL,
    "publicationYear" INTEGER NOT NULL,
    "evidenceSummary" TEXT NOT NULL,
    "sourceUrl" TEXT NOT NULL,

    CONSTRAINT "ScientificReference_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ScanIngredient" (
    "id" UUID NOT NULL,
    "scanId" UUID NOT NULL,
    "ingredientId" UUID NOT NULL,
    "detectedName" TEXT NOT NULL,
    "confidenceScore" DOUBLE PRECISION NOT NULL,

    CONSTRAINT "ScanIngredient_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "IngredientCategory" (
    "id" UUID NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,

    CONSTRAINT "IngredientCategory_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "IngredientBenefit" (
    "id" UUID NOT NULL,
    "ingredientId" UUID NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT NOT NULL,

    CONSTRAINT "IngredientBenefit_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "User_email_key" ON "User"("email");

-- CreateIndex
CREATE UNIQUE INDEX "User_username_key" ON "User"("username");

-- CreateIndex
CREATE INDEX "User_email_idx" ON "User"("email");

-- CreateIndex
CREATE INDEX "User_username_idx" ON "User"("username");

-- CreateIndex
CREATE INDEX "Scan_userId_idx" ON "Scan"("userId");

-- CreateIndex
CREATE INDEX "Scan_createdAt_idx" ON "Scan"("createdAt");

-- CreateIndex
CREATE UNIQUE INDEX "Ingredient_inciName_key" ON "Ingredient"("inciName");

-- CreateIndex
CREATE INDEX "Ingredient_inciName_idx" ON "Ingredient"("inciName");

-- CreateIndex
CREATE INDEX "IngredientAlias_ingredientId_idx" ON "IngredientAlias"("ingredientId");

-- CreateIndex
CREATE INDEX "IngredientAlias_alias_idx" ON "IngredientAlias"("alias");

-- CreateIndex
CREATE UNIQUE INDEX "SafetyProfile_ingredientId_key" ON "SafetyProfile"("ingredientId");

-- CreateIndex
CREATE INDEX "SafetyProfile_ingredientId_idx" ON "SafetyProfile"("ingredientId");

-- CreateIndex
CREATE INDEX "Regulation_ingredientId_idx" ON "Regulation"("ingredientId");

-- CreateIndex
CREATE INDEX "Regulation_country_idx" ON "Regulation"("country");

-- CreateIndex
CREATE INDEX "ScientificReference_ingredientId_idx" ON "ScientificReference"("ingredientId");

-- CreateIndex
CREATE INDEX "ScientificReference_publicationYear_idx" ON "ScientificReference"("publicationYear");

-- CreateIndex
CREATE INDEX "ScanIngredient_scanId_idx" ON "ScanIngredient"("scanId");

-- CreateIndex
CREATE INDEX "ScanIngredient_ingredientId_idx" ON "ScanIngredient"("ingredientId");

-- CreateIndex
CREATE UNIQUE INDEX "ScanIngredient_scanId_ingredientId_key" ON "ScanIngredient"("scanId", "ingredientId");

-- CreateIndex
CREATE UNIQUE INDEX "IngredientCategory_name_key" ON "IngredientCategory"("name");

-- CreateIndex
CREATE INDEX "IngredientBenefit_ingredientId_idx" ON "IngredientBenefit"("ingredientId");

-- AddForeignKey
ALTER TABLE "Scan" ADD CONSTRAINT "Scan_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Ingredient" ADD CONSTRAINT "Ingredient_categoryId_fkey" FOREIGN KEY ("categoryId") REFERENCES "IngredientCategory"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "IngredientAlias" ADD CONSTRAINT "IngredientAlias_ingredientId_fkey" FOREIGN KEY ("ingredientId") REFERENCES "Ingredient"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "SafetyProfile" ADD CONSTRAINT "SafetyProfile_ingredientId_fkey" FOREIGN KEY ("ingredientId") REFERENCES "Ingredient"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Regulation" ADD CONSTRAINT "Regulation_ingredientId_fkey" FOREIGN KEY ("ingredientId") REFERENCES "Ingredient"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ScientificReference" ADD CONSTRAINT "ScientificReference_ingredientId_fkey" FOREIGN KEY ("ingredientId") REFERENCES "Ingredient"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ScanIngredient" ADD CONSTRAINT "ScanIngredient_scanId_fkey" FOREIGN KEY ("scanId") REFERENCES "Scan"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ScanIngredient" ADD CONSTRAINT "ScanIngredient_ingredientId_fkey" FOREIGN KEY ("ingredientId") REFERENCES "Ingredient"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "IngredientBenefit" ADD CONSTRAINT "IngredientBenefit_ingredientId_fkey" FOREIGN KEY ("ingredientId") REFERENCES "Ingredient"("id") ON DELETE CASCADE ON UPDATE CASCADE;
