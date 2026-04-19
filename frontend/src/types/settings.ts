export interface Setting {
  key: string;
  value: string;
  description: string | null;
  input_type: 'url' | 'number' | 'text' | 'select' | 'password';
  options: string | null;
  category: string;
}