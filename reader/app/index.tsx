import { View, Text, StyleSheet } from 'react-native';

export default function LibraryMain() {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Library</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#F5F0EB' },
  title: { fontSize: 32, fontWeight: '700', color: '#2C2417' },
});
