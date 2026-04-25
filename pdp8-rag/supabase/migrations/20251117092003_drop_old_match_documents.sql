-- Drop the old match_documents function that uses vector type
DROP FUNCTION IF EXISTS match_documents(vector, integer, text);
