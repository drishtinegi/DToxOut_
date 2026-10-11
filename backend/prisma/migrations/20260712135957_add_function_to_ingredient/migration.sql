/*
  Warnings:

  - Added the required column `function` to the `Ingredient` table without a default value. This is not possible if the table is not empty.

*/
-- AlterTable
ALTER TABLE "Ingredient" ADD COLUMN     "function" TEXT NOT NULL;
