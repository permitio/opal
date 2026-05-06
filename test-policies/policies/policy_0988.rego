package governance.enforcement.policy.allow.policy_0988

# Auto-generated policy 988 (Rego v1 syntax)
# Package: governance.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0988",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0988_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0988_allowed if {
    input.user.role == "admin"
}
default policy_0988_allowed = false
