package risk.authorization.user.deny.policy_0889

# Auto-generated policy 889 (Rego v1 syntax)
# Package: risk.authorization.user.deny

# Metadata
metadata := {
    "policy_id": "0889",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0889_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0889_allowed if {
    input.user.role == "admin"
}
policy_0889_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
