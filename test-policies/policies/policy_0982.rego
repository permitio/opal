package compliance.authentication.user.deny.logic.policy_0982

# Auto-generated policy 982 (Rego v1 syntax)
# Package: compliance.authentication.user.deny.logic

# Metadata
metadata := {
    "policy_id": "0982",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0982_allowed if {
    data.policies.compliance.enabled
}
policy_0982_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
