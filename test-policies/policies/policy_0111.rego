package audit.authentication.policy.deny.policy_0111

# Auto-generated policy 111 (Rego v1 syntax)
# Package: audit.authentication.policy.deny

# Metadata
metadata := {
    "policy_id": "0111",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0111_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0111_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
