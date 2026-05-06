package risk.authorization.policy.check.policy_0639

# Auto-generated policy 639 (Rego v1 syntax)
# Package: risk.authorization.policy.check

# Metadata
metadata := {
    "policy_id": "0639",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0639_allowed = false
policy_0639_allowed if {
    data.policies.risk.enabled
}
policy_0639_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0639_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
