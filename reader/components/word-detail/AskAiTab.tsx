import { useState, useRef } from 'react';
import {
  View,
  Text,
  TextInput,
  Pressable,
  FlatList,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { useReaderStore } from '../../stores/reader';
import { Icon } from '../ui/Icon';
import { colors, spacing, borderRadius, typography } from '../../constants/theme';

const SUGGESTED_QUESTIONS = [
  'What root does this word come from?',
  'How does this word change with different pronouns?',
  'Give me an example sentence with this word.',
  'What are common mistakes with this word?',
];

export function AskAiTab() {
  const chatHistory = useReaderStore((s) => s.chatHistory);
  const isAiTyping = useReaderStore((s) => s.isAiTyping);
  const sendAiQuestion = useReaderStore((s) => s.sendAiQuestion);
  const selectedToken = useReaderStore((s) => s.selectedToken);

  const [inputText, setInputText] = useState('');
  const flatListRef = useRef<FlatList>(null);

  const handleSend = async (text?: string) => {
    const question = text ?? inputText.trim();
    if (!question) return;
    setInputText('');
    await sendAiQuestion(question);
    // Scroll to end after response
    setTimeout(() => {
      flatListRef.current?.scrollToEnd({ animated: true });
    }, 100);
  };

  const showSuggestions = chatHistory.length === 0;

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      keyboardVerticalOffset={120}
    >
      {/* Suggested questions when empty */}
      {showSuggestions && (
        <View style={styles.suggestionsContainer}>
          <Text style={styles.suggestionsLabel}>
            Ask about{' '}
            <Text style={styles.wordHighlight}>
              {selectedToken?.tashkeel ?? selectedToken?.text ?? 'this word'}
            </Text>
          </Text>
          <View style={styles.suggestionsList}>
            {SUGGESTED_QUESTIONS.map((q, i) => (
              <Pressable
                key={i}
                style={styles.suggestionChip}
                onPress={() => handleSend(q)}
              >
                <Text style={styles.suggestionText}>{q}</Text>
              </Pressable>
            ))}
          </View>
        </View>
      )}

      {/* Chat messages */}
      {chatHistory.length > 0 && (
        <FlatList
          ref={flatListRef}
          data={chatHistory}
          keyExtractor={(_, i) => i.toString()}
          style={styles.messageList}
          contentContainerStyle={styles.messageListContent}
          renderItem={({ item }) => (
            <View
              style={[
                styles.messageBubble,
                item.role === 'user' ? styles.userBubble : styles.aiBubble,
              ]}
            >
              <Text
                style={[
                  styles.messageText,
                  item.role === 'user' ? styles.userText : styles.aiText,
                ]}
              >
                {item.content}
              </Text>
            </View>
          )}
          ListFooterComponent={
            isAiTyping ? (
              <View style={[styles.messageBubble, styles.aiBubble]}>
                <ActivityIndicator size="small" color={colors.textSecondary} />
              </View>
            ) : null
          }
        />
      )}

      {/* Input row */}
      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={inputText}
          onChangeText={setInputText}
          placeholder="Ask anything about this word..."
          placeholderTextColor={colors.textTertiary}
          multiline
          returnKeyType="send"
          onSubmitEditing={() => handleSend()}
          editable={!isAiTyping}
        />
        <Pressable
          style={[styles.sendButton, (!inputText.trim() || isAiTyping) && styles.sendButtonDisabled]}
          onPress={() => handleSend()}
          disabled={!inputText.trim() || isAiTyping}
          accessibilityRole="button"
          accessibilityLabel="Send message"
        >
          <Icon name="arrow-up" size={18} color={colors.white} />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  suggestionsContainer: {
    flex: 1,
    gap: spacing.md,
    paddingTop: spacing.sm,
  },
  suggestionsLabel: {
    fontFamily: 'DMSans',
    fontSize: 14,
    color: colors.textSecondary,
  },
  wordHighlight: {
    fontFamily: 'NotoNaskhArabic-Bold',
    fontSize: 18,
    color: colors.textPrimary,
  },
  suggestionsList: {
    gap: spacing.sm,
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  suggestionChip: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.full,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  suggestionText: {
    fontFamily: 'DMSans',
    fontSize: 13,
    color: colors.textSecondary,
  },
  messageList: {
    flex: 1,
  },
  messageListContent: {
    gap: spacing.sm,
    paddingVertical: spacing.sm,
  },
  messageBubble: {
    maxWidth: '85%',
    borderRadius: borderRadius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  userBubble: {
    alignSelf: 'flex-end',
    backgroundColor: colors.primary,
    borderBottomRightRadius: 4,
  },
  aiBubble: {
    alignSelf: 'flex-start',
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    borderBottomLeftRadius: 4,
  },
  messageText: {
    ...typography.body,
  },
  userText: {
    fontFamily: 'DMSans',
    color: colors.white,
  },
  aiText: {
    fontFamily: 'DMSans',
    color: colors.textPrimary,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: spacing.sm,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.cardBorder,
  },
  input: {
    flex: 1,
    fontFamily: 'DMSans',
    fontSize: 15,
    color: colors.textPrimary,
    backgroundColor: colors.card,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
    maxHeight: 100,
  },
  sendButton: {
    width: 40,
    height: 40,
    borderRadius: borderRadius.full,
    backgroundColor: colors.accent,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendButtonDisabled: {
    backgroundColor: colors.cardBorder,
  },
});
