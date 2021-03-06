from enum import IntEnum
import sys
import argparse
import math
import random

class Card:
    def __init__(self, color, rank, value):
        self.color = color
        self.rank = rank
        self.value = value

    def __str__(self):
        return self.rank + " of " + self.color

    def __eq__(self, other):
        return self.color == other.color and self.rank == other.rank

def generate_deck(suits=["Hearts", "Spades", "Clubs", "Diamonds"],
                  ranks=[("2",2), ("3",3), ("4",4), ("5",5), ("6",6), ("7",7), ("8",8), ("9",9), ("10",10), ("Jack",10), ("Queen",10), ("King",10), ("Ace",11)]):
    result = []
    for suit in suits:
        for (rank,value) in ranks:
            result.append(Card(suit,rank,value))
    return result

def format(cards):
    if isinstance(cards, Card):
        return str(cards)
    return ", ".join(map(str, cards))

def get_value(cards):
    """
    Calculate the value of a set of cards. Aces may be counted as 11 or 1, to avoid going over 21
    """
    result = 0
    aces = 0
    for c in cards:
        result += c.value
        if c.rank == "Ace":
            aces += 1
    while result > 21 and aces > 0:
        result -= 10
        aces -= 1
    return result


class PlayerType(IntEnum):
    PLAYER = 1
    DEALER = 2

class Action(IntEnum):
    HIT = 1
    STAND = 2
    DOUBLE_DOWN = 3
    SPLIT = 4

class Player:
    """
    The basic player just chooses a random action
    """
    def __init__(self, name, deck):
        self.name = name
        self.deck = deck
    def get_action(self, cards, actions, dealer_cards):
        return random.choice(actions)
    def reset(self):
        pass

class TimidPlayer(Player):
    """
    The timid player always stands, and never takes additional cards.
    """
    def get_action(self, cards, actions, dealer_cards):
        return Action.STAND

class BasicStrategyPlayer(Player):
    """
    Basic strategy: If the dealer has a card lower than a 7 open, we hit if we have less than 12. Otherwise, we hit if we have less than 17. The idea being: If the dealer has a low card open, they are more likely to bust, if they have a high card open they are more likely to stand with a high score that we need to beat.
    """
    def get_action(self, cards, actions, dealer_cards):
        pval = get_value(cards)
        if dealer_cards[0].value < 7:
            if pval < 12:
                return Action.HIT
            return Action.STAND
        if pval < 17:
            return Action.HIT
        return Action.STAND

MCTS_N = 100


class MCTSTree:
    def __init__(self, root=False, parent=None, wins: int = 0, losses: int = 0):
        self.wins: int = wins
        self.losses: int = losses
        self.parent = parent

        # Assumes there will be 4 nodes all the time.
        # Index order follows the Action order from Action class.
        # [Hit, Stand, Double Down, Split] or
        # [Hit, Stand]
        if root:
            self.children = [None, None, None, None]
        else:
            self.children = [None, None]

    # index uses the value from Action class. No need to adjust the index value.
    def modify_children(self, obj, index):
        self.children[index - 1] = obj

    def get_wins(self) -> int:
        return self.wins

    def get_losses(self) -> int:
        return self.losses

    def get_children(self, index):
        return self.children[index]

    def get_parent(self):
        return self.parent

    def modify_wins(self, new_wins):
        self.wins = new_wins

    def modify_losses(self, new_losses):
        self.losses = new_losses

    def adjust_wins(self, wins_adjustment):
        self.wins = wins_adjustment

    def adjust_losses(self, loss_adjustment):
        self.losses = loss_adjustment

    def iterate_wins(self):
        self.wins += 1

    def iterate_losses(self):
        self.losses += 1


MCTS_N = 100

class WinLossTracker:
    def __init__(self):
        self.wins: int = 0
        self.losses: int = 0

    def get_wins(self):
        return self.wins

    def get_losses(self):
        return self.losses

    def increment_wins(self):
        self.wins = self.wins + 1

    def increment_losses(self):
        self.losses = self.losses + 1

    def reset_wins(self):
        self.wins = 0

    def reset_losses(self):
        self.losses = 0

    def reset_all(self):
        self.wins = 0
        self.losses = 0

WinLossTrack = WinLossTracker()
ActionDictionary = {Action.HIT: 1, Action.STAND: 2, Action.DOUBLE_DOWN: 3, Action.SPLIT: 4}

class MCTSPlayer(Player):
    """
    MCTSPlayer we need to implement for the lab.
    """

    def __init__(self, name, deck):
        self.name = name
        self.bet = 2
        self.deck = deck

    def get_action(self, cards, actions, dealer_cards):

        main_current_node = MCTSTree()
        # Make a copy of the deck!
        deck = self.deck[:]

        # Remove cards we have already seen (ours, and the open dealer card)
        for p in cards:
            deck.remove(p)
        for p in dealer_cards:
            deck.remove(p)

        # For each of our simulations we use the rollout player.
        # Our Rollout Player selects actions at random, and records what it did (!)
        p = RolloutPlayer("Rollout", deck)

        # We create a new game object with the reduced deck, played by our rollout player
        g1 = Game(deck, p, verbose=False)

        results = {}
        for i in range(MCTS_N):

            # The rollout player stores its action history, we reset this first
            p.reset()

            node_check = -1
            while node_check == -1:
                node_check = MCTSPlayer.NodeChecker(self, current_node=main_current_node)
                if node_check != -1:
                    MCTSPlayer.MCTSExpansion(self, current_node=main_current_node, children_node_index=node_check)
                    MCTSPlayer.MCTSSimulation(self, current_node=main_current_node)
                else:
                    MCTSPlayer.RouletteWheelSelection(self, current_node=main_current_node)

            # continue_round allows us to pass a partial game state (which cards we have, what the open
            # card of the dealer is, and how much we've bet), and continue the game from there
            # i.e. the game will *not* deal us two new cards, but instead use the ones we already have
            # It will, however, then run as normal, calling `get_action` on the player object we passed earlier,
            # which is our rollout_player
            # The return value is the amount of money the agent won, across *all* hands (if they split)
            res = g1.continue_round(cards, dealer_cards, self.bet)
            if res > 0:
                WinLossTrack.increment_wins()
            elif res < 0:
                WinLossTrack.increment_losses()

            # After we are done, we extract the first action we took
            act = p.actions[0]
            action_number = ActionDictionary.get(act)

            # Record the result for each possible action
            if act not in results:
                results[act] = []
            results[act].append(res)
        print(results)

        # Calculate the action with the highest *average* return
        max = -1000
        act = Action.STAND
        avgs = {}
        for a in results:
            score = sum(results[a]) * 1.0 / len(results[a])
            avgs[a] = score
            if score > max:
                max = score
                act = a

        # Make sure we also record our own bet in case we double down (!)
        if act == Action.DOUBLE_DOWN:
            self.bet *= 2
        return act

    def reset(self):
        self.bet = 2

    # Randomly select an action based on the number of wins and losses.
    def RouletteWheelSelection(self, current_node):
        nodes_list_length: int = len(current_node.children)
        print(current_node.children)
        node_weight_sum: int = 0
        node_weight_list = []
        counter = 0

        # Calculate the node weight and append to node weight list
        while counter < nodes_list_length:
            node_weight_temp = min(1, math.ceil(
            current_node.children[counter].wins / (current_node.children[counter].wins + current_node.children[counter].losses) * 100))
            node_weight_list.append(node_weight_temp)
            node_weight_sum += node_weight_temp
            counter += 1

        # Randomize number using the calculated node weights + 1
        random_result = random.randrange(node_weight_sum + 1)
        random_result_index = 0
        calculation_in_progress = True

        counter = 0

        # Loop until the random_result is less than or equal to the current node weight value
        # If the value is greater, subtract the current node weight value to the random_result
        while calculation_in_progress and counter < nodes_list_length:
            net_weight_subtract = node_weight_list.pop()

            if random_result <= net_weight_subtract:
                random_result_index = counter
                calculation_in_progress = False
            else:
                random_result -= net_weight_subtract
                counter += 1

        return random_result_index

    def MCTSActionSelection(self, current_node):
        children_node_index = MCTSPlayer.NodeChecker(self, current_node)

        if children_node_index == -1:
            MCTSPlayer.RouletteWheelSelection(self, current_node)
        else:
            MCTSPlayer.MCTSExpansion(self, current_node, children_node_index)
            MCTSPlayer.MCTSSimulation(self, current_node)

    # Checks if the action is fully expanded.
    # Returns the index number if there is children with None value.
    # Otherwise, return -1 if all nodes are expanded.
    def NodeChecker(self, current_node):
        node_length = len(current_node.children)
        counter = 0

        while counter < node_length:
            if current_node.children[counter] is None:
                return counter
            else:
                counter += 1

        if counter is node_length:
            return -1

    # Initialize new node with MCTSTree class and assign
    def MCTSExpansion(self, current_node, children_node_index):
        new_node = MCTSTree(root=False, parent=None, wins=0, losses=0)
        current_node.modify_children(new_node, children_node_index)

    def MCTSSimulation(self, current_node):
        # TODO - Code for simulation here?
        # Note - Save current state and then simulate actions randomly multiple times for the initial MCTS node.
        # Note - Simulation code is currently missing.

        children_node_index = MCTSPlayer.NodeChecker(self, current_node)
        WinLossTrack.reset_all()
        '''
        while True:
            if current_node != -1:
                return 1 - game_results if invert_results else game_results
            invert_results = not invert_results
        '''
        random_integer = random.randint(0, 1)
        wins = 0
        losses = 0
        if random_integer:
            wins = 1
        else:
            losses = 1

        new_node = MCTSTree(root=False, parent=None, wins=wins, losses=losses)
        current_node.modify_children(new_node, children_node_index)
        current_node = new_node

    # Backpropagate using the Tree node's parents variable.
    def Backpropagation(self, current_node, game_results: bool):
        current_backpropagation_node = current_node
        while current_backpropagation_node is not None:
            if game_results:
                current_backpropagation_node.iterate_wins()
            else:
                current_backpropagation_node.iterate_losses()

            current_backpropagation_node = current_backpropagation_node.get_parent()

"""Given MCTS-N Player"""
# class MCTSPlayer(Player):
#     """
#     This is only a demonstration, not *actual* Monte Carlo Tree Search!
#
#     This agent will run MCTS_N simulations. For each simulation, the cards the player has not yet seen are shuffled and used as the assumed deck. Then the `RolloutPlayer` plays MCTS_N games starting from that random shuffle
#     The agent will only remember the *first* action taken by the `RolloutPlayer` and how many points where obtained
#     on average for each possible action.
#     """
#     def __init__(self, name, deck):
#         self.name = name
#         self.bet = 2
#         self.deck = deck
#
#     def get_action(self, cards, actions, dealer_cards):
#
#         # Make a copy of the deck!
#         deck = self.deck[:]
#
#         # Remove cards we have already seen (ours, and the open dealer card)
#         for p in cards:
#             deck.remove(p)
#         for p in dealer_cards:
#             deck.remove(p)
#
#         # For each of our simulations we use the rollout player.
#         # Our Rollout Player selects actions at random, and records what it did (!)
#         p = RolloutPlayer("Rollout", deck)
#
#         # We create a new game object with the reduced deck, played by our rollout player
#         g1 = Game(deck, p, verbose=False)
#
#         results = {}
#         for i in range(MCTS_N):
#
#             # The rollout player stores its action history, we reset this first
#             p.reset()
#
#             # continue_round allows us to pass a partial game state (which cards we have, what the open
#             # card of the dealer is, and how much we've bet), and continue the game from there
#             # i.e. the game will *not* deal us two new cards, but instead use the ones we already have
#             # It will, however, then run as normal, calling `get_action` on the player object we passed earlier,
#             # which is our rollout_player
#             # The return value is the amount of money the agent won, across *all* hands (if they split)
#             res = g1.continue_round(cards, dealer_cards, self.bet)
#
#             # After we are done, we extract the first action we took
#             act = p.actions[0]
#
#             # Record the result for each possible action
#             if act not in results:
#                 results[act] = []
#             results[act].append(res)
#
#         # Calculate the action with the highest *average* return
#         max = -1000
#         act = Action.STAND
#         avgs = {}
#         for a in results:
#             score = sum(results[a])*1.0/len(results[a])
#             avgs[a] = score
#             if score > max:
#                 max = score
#                 act = a
#
#         # Make sure we also record our own bet in case we double down (!)
#         if act == Action.DOUBLE_DOWN:
#             self.bet *= 2
#         return act
#     def reset(self):
#         self.bet = 2

class RolloutPlayer(Player):
    """
    Used by the MCTS Player to perform rollouts: play randomly and record actions
    """
    def __init__(self, name, deck):
        self.name = name
        self.actions = []
        self.deck = deck
    def get_action(self, cards, actions, dealer_cards):
        act = random.choice(actions)
        self.actions.append(act)
        return act
    def reset(self):
        self.actions = []

class ConsolePlayer(Player):
    def get_action(self, cards, actions, dealer_cards):
        print()
        print("  Your cards:", format(cards), "(%.1f points)"%get_value(cards))
        print("  Dealer's visible card:", format(dealer_cards), "(%.1f points)"%get_value(dealer_cards))
        while True:
            print("  Which action do you want to take?")
            for i, a in enumerate(actions):
                print(" ", i+1, a.name)
            x = input()
            try:
                x = int(x)
                return actions[x-1]
            except Exception:
                print(" >>> Please enter a valid action number <<<")
    def reset(self):
        pass

class Dealer(Player):
    """
    The dealer has a fixed strategy: Hit when he has fewer than 17 points, otherwise stand.
    """
    def __init__(self):
        self.name = "Dealer"
    def get_action(self, cards, actions, dealer_cards):
        if get_value(cards) < 17:
            return Action.HIT
        return Action.STAND

def same_rank(a, b):
    return a.rank == b.rank

def same_value(a, b):
    return a.value == b.value


class Game:
    def __init__(self, cards, player, split_rule=same_value, verbose=True):
        self.cards = cards
        self.player = player
        self.dealer = Dealer()
        self.dealer_cards = []
        self.player_cards = []
        self.split_cards = []
        self.verbose = verbose
        self.split_rule = split_rule

    def round(self):
        """
        Play one round of black jack. First, the player is asked to take actions until they
        either stand or have more than 21 points. The return value of this function is the
        amount of money the player won.
        """
        self.deck = self.cards[:]
        random.shuffle(self.deck)
        self.dealer_cards = []
        self.player_cards = []
        self.bet = 2
        self.player.reset()
        self.dealer.reset()
        for i in range(2):
            self.deal(self.player_cards, self.player.name)
            self.deal(self.dealer_cards, self.dealer.name, i < 1)
        return self.play_round()


    def continue_round(self, player_cards, dealer_cards, bet):
        """
        Like round, but allows passing an initial game state in order to finish a partially played game.

        player_cards are the cards the player has in their hand
        dealer_cards are the visible cards (typically 1) of the dealer
        bet is the current bet of the player

        Note: For best results create a *new* Game object with a deck that has player_cards and dealer_cards removed.
        """
        self.deck = self.cards[:]
        random.shuffle(self.deck)
        self.bet = bet
        self.player_cards = player_cards[:]
        self.dealer_cards = dealer_cards[:]
        while len(self.dealer_cards) < 2:
            self.deal(self.dealer_cards, self.dealer.name)
        return self.play_round()

    def play_round(self):
        """
        Function used to actually play a round of blackjack after the initial setup done in round or continue_round.

        Will first let the player take their actions and then proceed with the dealer.
        """
        cards = self.play(self.player, self.player_cards)
        if self.verbose:
            print("Dealer reveals: ", format(self.dealer_cards[-1]))
            print("Dealer has:", format(self.dealer_cards), "(%.1f points)"%get_value(self.dealer_cards))
        self.play(self.dealer, self.dealer_cards)
        reward = sum(self.reward(c) for c in cards)
        if self.verbose:
            print("Bet:", self.bet, "won:", reward, "\n")
        return reward

    def deal(self, cards, name, public=True):
        """
        Deal the next card to the given hand
        """
        card = self.deck[0]
        if self.verbose and public:
            print(name, "draws", format(card))
        self.deck = self.deck[1:]
        cards.append(card)

    def play(self, player, cards, cansplit=True, postfix=""):
        """
        Play a round of blackjack for *one* participant (player or dealer).

        Note that a player may only split once, and only if the split_rule is satisfied (either two cards of the same rank, or of the same value)
        """
        while get_value(cards) < 21:
            actions = [Action.HIT, Action.STAND, Action.DOUBLE_DOWN]
            if len(cards) == 2 and cansplit and self.split_rule(cards[0], cards[1]):
                actions.append(Action.SPLIT)
            act = player.get_action(cards, actions, self.dealer_cards[:1])
            if act in actions:
                if self.verbose:
                    print(player.name, "does", act.name)
                if act == Action.STAND:
                    break
                if act == Action.HIT or act == Action.DOUBLE_DOWN:
                    self.deal(cards, player.name)
                if act == Action.DOUBLE_DOWN:
                    self.bet *= 2
                    break
                if act == Action.SPLIT:
                    pilea = cards[:1]
                    pileb = cards[1:]
                    if self.verbose:
                        print(player.name, "now has 2 hands")
                        print("Hand 1:", format(pilea))
                        print("Hand 2:", format(pileb))
                    self.play(player, pilea, False, " (hand 1)")
                    self.play(player, pileb, False, " (hand 2)")
                    return [pilea, pileb]
        if self.verbose:
            print(player.name, "ends with%s"%(postfix), format(cards), "with value", get_value(cards), "\n")
        return [cards]

    def reward(self, player_cards):
        """
        Calculate amount of money won by the player. Blackjack pays 3:2.
        """
        pscore = get_value(player_cards)
        dscore = get_value(self.dealer_cards)
        if self.verbose:
            print(self.player.name + ":", format(player_cards), "(%.1f points)"%(pscore))
            print(self.dealer.name + ":", format(self.dealer_cards), "(%.1f points)"%(dscore))

        if pscore > 21:
            return -self.bet
        result = -self.bet
        if pscore > dscore or dscore > 21:
            if pscore == 21 and len(self.player_cards) == 2:
                result = 3*self.bet/2
            result = self.bet
        if pscore == dscore and (pscore != 21 or len(self.player_cards) != 2):
            result = 0
        return result


player_types = {"default": Player, "timid": TimidPlayer, "basic": BasicStrategyPlayer, "mcts": MCTSPlayer, "console": ConsolePlayer}

# Our implementation allows us to define different deck "types", such as only even cards,
# or even use made-up card values like "1.5"

deck_types = {"default": generate_deck(),
              "high": generate_deck(ranks=[("2", 2), ("10", 10), ("Ace", 11), ("Fool", 12)]),
              "low": generate_deck(ranks=[("1.5", 1.5), ("2", 2),("2.2", 2.2), ("3", 3), ("3", 4), ("Ace", 11)], suits=["Hearts", "Spades", "Clubs", "Diamonds", "Swords", "Wands", "Bows"]),
              "even": generate_deck(ranks=[("2",2), ("4",4), ("6",6), ("8",8), ("10",10), ("Jack",10), ("Queen",10), ("King",10)]),
              "odd": generate_deck(ranks=[("3",3), ("5",5), ("7",7), ("9",9), ("Ace",11)]),
              "red": generate_deck(suits=["Diamonds", "Hearts"]),
              "random": generate_deck(ranks=random.sample([("2",2), ("3",3), ("4",4), ("5",5), ("6",6), ("7",7), ("8",8), ("9",9), ("10",10), ("Jack",10), ("Queen",10), ("King",10), ("Ace",11)], random.randint(5,13)))}

def main(ptype="default", dtype="default", n=100, split_rule=same_value, verbose=True):
    deck = deck_types[dtype]
    g = Game(deck, player_types[ptype]("Sir Gladington III, Esq.", deck[:]), split_rule, verbose)
    points = []
    for i in range(n):
        points.append(g.round())
    print("Average points: ", sum(points)*1.0/n)


# run `python blackjack.py --help` for usage information
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run a simulation of a Blackjack agent.')
    parser.add_argument('player', nargs="?", default="default",
                        help='the player type (available values: %s)'%(", ".join(player_types.keys())))
    parser.add_argument('-n', '--count', dest='count', action='store', default=100,
                        help='How many games to run')
    parser.add_argument('-s', '-q', '--silent', '--quiet', dest='verbose', action='store_const', default=True, const=False,
                        help='Do not print game output (only average score at the end is printed)')
    parser.add_argument('-r', '--rank', '--rank-split', dest='split', action='store_const', default=same_value, const=same_rank,
                        help="Only allow split when the player's cards have the same rank (default: allow split when they have the same value)")
    parser.add_argument('-d', "--deck", metavar='D', dest="deck", nargs=1, default=["default"],
                        help='the deck type to use (available values: %s)'%(", ".join(deck_types.keys())))
    args = parser.parse_args()
    if args.player not in player_types:
        print("Invalid player type: %s. Available options are: \n%s"%(args.player, ", ".join(player_types.keys())))
        sys.exit(-1)
    if args.deck[0] not in deck_types:
        print("Invalid deck type: %s. Available options are: \n%s"%(args.deck, ", ".join(deck_types.keys())))
        sys.exit(-1)
    main("default", "", int(args.count), args.split, args.verbose)